import base64
import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from backend.store import Fault, Store, totp_ok


def device():
    private = ec.generate_private_key(ec.SECP256R1())
    public = base64.b64encode(private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    return private, public


def proof(store, private, public, purpose):
    challenge = store.challenge(public, purpose)
    return {'public_key': public, 'challenge_id': challenge['id'],
            'signature': base64.b64encode(private.sign(challenge['message'].encode(), ec.ECDSA(hashes.SHA256()))).decode()}


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = [1_800_000_000]
        self.store = Store(Path(self.tmp.name) / 'test.sqlite3', lambda:self.clock[0])
        self.private, self.public = device()
        self.profile = self.store.save_profile({'name':'MTN pilot','carrier':'MTN','server':'vpn.example.com','port':443,'sni':'vpn.example.com','tls_min':'1.2','enabled':True})

    def tearDown(self):
        self.tmp.cleanup()

    def issue(self, duration=86400*15, quota=10000, kind='paid'):
        return self.store.issue({'label':'Customer','kind':kind,'duration_seconds':duration,'quota_bytes':quota,'profile_ids':[self.profile['id']]})

    def activate(self, item, private=None, public=None):
        return self.store.activate(dict(proof(self.store, private or self.private, public or self.public, 'activate'), code=item['code']))

    def tunnel(self, result):
        ticket = self.store.connect(result['token'], dict(proof(self.store,self.private,self.public,'connect'), profile_id=self.profile['id']))
        return self.store.open_tunnel(ticket['ticket'], 'vpn.example.com', 'TLSv1.3')

    def test_first_activation_and_reentry_never_restart_clock(self):
        item=self.issue();self.assertIsNone(item['account']['activated']);self.clock[0]+=500
        a=self.activate(item);expiry=self.clock[0]+15*86400;self.assertEqual(a['account']['expires'],expiry)
        self.clock[0]+=600;again=self.activate(item);self.assertEqual(again['account']['expires'],expiry)

    def test_trial_custom_hours(self):
        for hours in [1,3,17]:
            a=self.activate(self.issue(hours*3600,100000,'trial'))
            self.assertEqual(a['account']['expires']-a['account']['activated'],hours*3600)

    def test_admin_can_shorten_trial_after_activation(self):
        item=self.issue(duration=10800,kind='trial');a=self.activate(item);self.clock[0]+=4000
        changed=self.store.update_account(a['account']['id'],{'duration_seconds':3600})
        self.assertEqual(changed['status'],'expired');self.assertEqual(changed['expires'],a['account']['activated']+3600)

    def test_seven_and_thirty_day_plans(self):
        for days in [7,30]:
            a=self.activate(self.issue(days*86400));self.assertEqual(a['account']['expires']-self.clock[0],days*86400)

    def test_code_bound_to_device(self):
        item=self.issue();self.activate(item)
        with self.assertRaises(Fault):self.activate(item,*device())

    def test_replayed_proof_rejected(self):
        item=self.issue();data=dict(proof(self.store,self.private,self.public,'activate'),code=item['code'])
        self.store.activate(data)
        with self.assertRaises(Fault):self.store.activate(data)

    def test_tampered_signature_rejected(self):
        data=dict(proof(self.store,self.private,self.public,'activate'),code=self.issue()['code']);data['signature']='AAAA'
        with self.assertRaises(Fault):self.store.activate(data)

    def test_wrong_purpose_rejected(self):
        with self.assertRaises(Fault):self.store.activate(dict(proof(self.store,self.private,self.public,'connect'),code=self.issue()['code']))

    def test_expired_challenge_rejected(self):
        item=self.issue();data=dict(proof(self.store,self.private,self.public,'activate'),code=item['code']);self.clock[0]+=61
        with self.assertRaises(Fault):self.store.activate(data)

    def test_invalid_codes_and_quotas(self):
        for quota in [0,-1,True,'1',10**16]:
            with self.assertRaises(Fault):self.issue(quota=quota)
        with self.assertRaises(Fault):self.activate({'code':'not-a-code'})

    def test_atomic_concurrent_activation_only_one_device(self):
        item=self.issue();devices=[device() for _ in range(6)]
        data=[dict(proof(self.store,pubprivate,pub,'activate'),code=item['code']) for pubprivate,pub in devices]
        def attempt(d):
            try:self.store.activate(d);return True
            except Fault:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:self.assertEqual(sum(pool.map(attempt,data)),1)

    def test_quota_no_overshoot_and_both_directions(self):
        a=self.activate(self.issue(quota=100));s=self.tunnel(a)
        self.store.consume(s['id'],60,'up');self.store.consume(s['id'],40,'down')
        with self.assertRaises(Fault):self.store.consume(s['id'],1)
        self.assertEqual(self.store.account(s['account'])['used'],100)

    def test_concurrent_quota_charge_atomic(self):
        a=self.activate(self.issue(quota=100));s=self.tunnel(a)
        def charge(_):
            try:self.store.consume(s['id'],15);return True
            except Fault:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(charge,range(20))),6)
        self.assertEqual(self.store.account(s['account'])['used'],90)

    def test_one_concurrent_session(self):
        a=self.activate(self.issue());self.tunnel(a)
        with self.assertRaises(Fault):self.tunnel(a)

    def test_private_addresses_are_not_reused_across_accounts(self):
        first=self.activate(self.issue());s1=self.tunnel(first);self.store.close_tunnel(s1['id']);self.store.delete_account(first['account']['id'])
        second=self.activate(self.issue());s2=self.tunnel(second);self.assertNotEqual(s1['slot'],s2['slot'])

    def test_reconnect_keeps_same_account_address(self):
        a=self.activate(self.issue());s1=self.tunnel(a);self.store.close_tunnel(s1['id']);s2=self.tunnel(a);self.assertEqual(s1['slot'],s2['slot'])

    def test_single_use_ticket(self):
        a=self.activate(self.issue());t=self.store.connect(a['token'],dict(proof(self.store,self.private,self.public,'connect'),profile_id=self.profile['id']))
        s=self.store.open_tunnel(t['ticket'],'vpn.example.com','TLSv1.3');self.store.close_tunnel(s['id'])
        with self.assertRaises(Fault):self.store.open_tunnel(t['ticket'],'vpn.example.com','TLSv1.3')

    def test_expiry_revokes_tunnel_even_without_client_polling(self):
        a=self.activate(self.issue(duration=3600));s=self.tunnel(a);self.clock[0]+=3600
        with self.assertRaises(Fault):self.store.consume(s['id'])
        with self.assertRaises(Fault):self.activate({'code':'invalid'})

    def test_suspend_and_delete_revoke(self):
        a=self.activate(self.issue());s=self.tunnel(a);self.store.update_account(s['account'],{'suspended':True})
        with self.assertRaises(Fault):self.store.consume(s['id'])
        self.store.update_account(s['account'],{'suspended':False});self.store.delete_account(s['account'])
        with self.assertRaises(Fault):self.store.client_auth(a['token'])
        with self.assertRaises(Fault):self.store.consume(s['id'])

    def test_profile_updates_revoke_old_sessions(self):
        a=self.activate(self.issue());s=self.tunnel(a);data={k:self.profile[k] for k in ['name','carrier','server','port','sni','tls_min','enabled']};data['enabled']=True;data['port']=8443
        self.store.save_profile(data,self.profile['id'])
        with self.assertRaises(Fault):self.store.consume(s['id'])

    def test_rebind_preserves_expiry(self):
        item=self.issue();a=self.activate(item);expiry=a['account']['expires'];self.clock[0]+=1000
        self.store.update_account(a['account']['id'],{'reset_device':True})
        p,k=device();again=self.activate(item,p,k);self.assertEqual(again['account']['expires'],expiry)
        with self.assertRaises(Fault):self.activate(item)

    def test_renewal_and_quota_edit(self):
        a=self.activate(self.issue());expiry=a['account']['expires'];row=self.store.update_account(a['account']['id'],{'extend_seconds':86400*7,'quota_bytes':20000})
        self.assertEqual(row['expires'],expiry+86400*7);self.assertEqual(row['quota'],20000)

    def test_password_session_logout(self):
        self.store.bootstrap('admin','A private test password 123!')
        with self.assertRaises(Fault):self.store.login('admin','wrong')
        t=self.store.login('admin','A private test password 123!');self.store.admin_auth(t);self.store.logout(t)
        with self.assertRaises(Fault):self.store.admin_auth(t)

    def test_totp_rfc_vector(self):
        secret=base64.b32encode(b'12345678901234567890').decode()
        self.assertTrue(totp_ok(secret,'287082',59));self.assertFalse(totp_ok(secret,'000000',59))

    def test_cleartext_secrets_not_stored(self):
        item=self.issue();a=self.activate(item)
        with self.store.db() as db:
            text=' '.join(str(tuple(r)) for t in ['accounts','tokens','audit'] for r in db.execute('SELECT * FROM '+t))
        self.assertNotIn(item['code'],text);self.assertNotIn(a['token'],text)

    def test_sni_and_tls_policy(self):
        a=self.activate(self.issue());t=self.store.connect(a['token'],dict(proof(self.store,self.private,self.public,'connect'),profile_id=self.profile['id']))
        with self.assertRaises(Fault):self.store.open_tunnel(t['ticket'],'wrong.example.com','TLSv1.3')


if __name__=='__main__':unittest.main()
