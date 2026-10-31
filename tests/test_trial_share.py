"""Trial account shared-device and shared-quota regression tests."""
import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from backend.store import Store, Fault, digest
from backend import xray
from tests.test_control import device, proof
from tests.test_xray import config


class TrialSharingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = [1_800_000_000]
        self.store = Store(Path(self.tmp.name) / 'trial.sqlite3', lambda:self.clock[0])
        self.profile = xray.save(self.store, {'name':'Shared trial','carrier':'Any','config':config(),'enabled':True})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def issue(self, kind='trial', quota=100, duration=3600):
        return self.store.issue({'label':'Shared', 'kind':kind,
                                 'duration_seconds':duration, 'quota_bytes':quota,
                                 'profile_ids':[self.profile['id']]})

    def activate(self, code, identity):
        private, public = identity
        return self.store.activate(dict(proof(self.store,private,public,'activate'),code=code))

    def connect(self, auth, identity):
        private, public = identity
        return xray.connect(self.store,auth['token'],
                            dict(proof(self.store,private,public,'connect'),profile_id=self.profile['id']))

    def test_one_trial_code_50_devices_shared_expiry_and_tokens(self):
        issued=self.issue()
        first=device()
        first_auth=self.activate(issued['code'],first)
        deadline=first_auth['account']['expires']
        devices=[first] + [device() for _ in range(49)]
        for identity in devices[1:]:
            self.activate(issued['code'],identity)
        data=self.store.account(issued['account']['id'])
        self.assertEqual((data['device_count'], data['device_limit']), (50,50))
        self.assertEqual((data['expires'],data['quota']), (deadline,100))
        self.assertEqual(self.store.client_auth(first_auth['token'])['auth_device_key'],first[1])
        with self.assertRaises(Fault) as error:
            self.activate(issued['code'],device())
        self.assertEqual(error.exception.status,409)
        self.clock[0]+=10
        self.activate(issued['code'],first)
        self.assertEqual(self.store.account(issued['account']['id'])['expires'],deadline)

    def test_paid_codes_remain_one_device_only(self):
        issued=self.issue('paid')
        first=device()
        self.activate(issued['code'],first)
        with self.assertRaises(Fault):
            self.activate(issued['code'],device())
        self.assertEqual(self.store.account(issued['account']['id'])['device_limit'],1)

    def test_parallel_sessions_use_one_shared_quota_and_isolate_devices(self):
        issued=self.issue(quota=100)
        devices=[device() for _ in range(3)]
        auth=[self.activate(issued['code'],d) for d in devices]
        leases=[self.connect(a,d) for a,d in zip(auth,devices)]
        with self.assertRaises(Fault):
            xray.heartbeat(self.store,auth[1]['token'],{'lease':leases[0]['lease'],'up':1,'down':0})
        xray.heartbeat(self.store,auth[0]['token'],{'lease':leases[0]['lease'],'up':20,'down':10})
        xray.heartbeat(self.store,auth[1]['token'],{'lease':leases[1]['lease'],'up':20,'down':10})
        xray.disconnect(self.store,auth[0]['token'],{'lease':leases[0]['lease']})
        self.assertTrue(xray.heartbeat(self.store,auth[1]['token'],
                        {'lease':leases[1]['lease'],'up':25,'down':15})['ok'])
        with self.assertRaises(Fault):
            xray.heartbeat(self.store,auth[2]['token'],
                           {'lease':leases[2]['lease'],'up':60,'down':60})
        data=self.store.account(issued['account']['id'])
        self.assertEqual((data['used'],data['remaining_bytes'],data['status']),(100,0,'depleted'))
        for identity, a in zip(devices,auth):
            with self.assertRaises(Fault):
                self.connect(a,identity)

    def test_renewing_device_token_does_not_revoke_another_device(self):
        issued=self.issue()
        first,second=device(),device()
        a=self.activate(issued['code'],first)
        b=self.activate(issued['code'],second)
        old=a['token']
        replacement=self.activate(issued['code'],first)
        with self.assertRaises(Fault):
            self.store.client_auth(old)
        self.assertEqual(self.store.client_auth(b['token'])['auth_device_key'],second[1])
        self.assertEqual(self.store.client_auth(replacement['token'])['auth_device_key'],first[1])

    def test_device_reset_preserves_shared_usage_and_expiry(self):
        issued=self.issue()
        a=self.activate(issued['code'],device())
        self.activate(issued['code'],device())
        expires=a['account']['expires']
        self.store.update_account(issued['account']['id'],{'reset_device':True})
        data=self.store.account(issued['account']['id'])
        self.assertEqual(data['device_count'],0)
        self.assertEqual(data['expires'],expires)
        with self.assertRaises(Fault):self.store.client_auth(a['token'])
        self.assertEqual(self.activate(issued['code'],device())['account']['device_count'],1)

    def test_migrates_legacy_trial_token_and_session_without_changing_expiry(self):
        issued=self.issue()
        identity=device()
        a=self.activate(issued['code'],identity)
        old=self.connect(a,identity)
        with self.store.db() as db:
            row=db.execute('SELECT * FROM trial_tokens WHERE account=?',(issued['account']['id'],)).fetchone()
            session=db.execute('SELECT * FROM trial_xray_sessions WHERE account=?',(issued['account']['id'],)).fetchone()
            db.execute('DELETE FROM trial_tokens WHERE account=?',(issued['account']['id'],))
            db.execute('DELETE FROM trial_xray_sessions WHERE account=?',(issued['account']['id'],))
            db.execute('DELETE FROM trial_devices WHERE account=?',(issued['account']['id'],))
            db.execute('INSERT INTO tokens(hash,account,expires) VALUES(?,?,?)',(row['hash'],row['account'],row['expires']))
            db.execute('INSERT INTO xray_sessions(account,profile,version,lease,seen,up,down) VALUES(?,?,?,?,?,?,?)',
                       (session['account'],session['profile'],session['version'],session['lease'],
                        session['seen'],session['up'],session['down']))
        self.store.close()
        self.store=Store(Path(self.tmp.name)/'trial.sqlite3',lambda:self.clock[0])
        self.assertEqual(self.store.client_auth(a['token'])['auth_device_key'],identity[1])
        self.assertEqual(self.store.account(issued['account']['id'])['device_count'],1)
        self.assertTrue(xray.heartbeat(self.store,a['token'],{'lease':old['lease'],'up':0,'down':1})['ok'])

    def test_concurrent_activation_limit_is_atomic(self):
        issued=self.issue()
        devices=[device() for _ in range(52)]
        def attempt(identity):
            try:
                self.activate(issued['code'],identity)
                return True
            except Fault as error:
                self.assertEqual(error.status,409)
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            accepted=list(pool.map(attempt,devices))
        self.assertEqual(sum(accepted),50)
        self.assertEqual(self.store.account(issued['account']['id'])['device_count'],50)


if __name__=='__main__':
    unittest.main()
