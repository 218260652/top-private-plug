import json
import tempfile
import unittest
from pathlib import Path
from backend import xray
from backend.store import Store, Fault
from tests.test_control import device, proof
from tests import test_api


def config(insecure=False):
    return {'dns': {'servers': ['tcp+local://1.1.1.1']}, 'inbounds': [{'listen':'0.0.0.0','port':1080,'protocol':'socks'}],
        'outbounds': [{'protocol':'trojan','tag':'original', 'settings': {'servers': [{'address':'vpn.example.com','port':443,'password':'test-secret-only'}]},
        'streamSettings': {'network':'tcp','security':'tls','tlsSettings': {'serverName':'vpn.example.com','allowInsecure':insecure}},
        'proxySettings': {'tag':'proxy','transportLayer':True}},
        {'tag':'proxy','protocol':'http','settings': {'servers':[{'address':'192.0.2.1','port':8080}], 'headers':{'Host':'vpn.example.com:443'}}}]}


class XrayTests(unittest.TestCase):
    @staticmethod
    def vless_config():
        raw = config(True)
        tunnel = raw['outbounds'][0]
        tunnel['protocol'] = 'vless'
        tunnel['settings'] = {'vnext': [{'address': 'vpn.example.com', 'port': 8446,
            'users': [{'id': '00000000-0000-4000-8000-000000000001', 'encryption': 'none', 'level': 8}]}]}
        tunnel['streamSettings']['tlsSettings']['fingerprint'] = 'chrome'
        tunnel['streamSettings']['wsSettings'] = {'path': '/unused'}
        raw['dns']['servers'] = ['https://1.1.1.1/dns-query', 'https://dns.google/dns-query']
        return raw

    def test_vless_preserves_credentials_proxy_fingerprint_and_routed_doh(self):
        raw = self.vless_config()
        original = json.loads(json.dumps(raw))
        normalized, address, port, sni, insecure = xray.normalize(raw, True)
        tunnel = normalized['outbounds'][0]
        self.assertEqual(tunnel['protocol'], 'vless')
        self.assertNotIn('servers', tunnel['settings'])
        self.assertEqual(tunnel['settings']['vnext'][0]['users'][0]['id'],
                         raw['outbounds'][0]['settings']['vnext'][0]['users'][0]['id'])
        self.assertEqual((address, port, sni, insecure), ('vpn.example.com', 8446, 'vpn.example.com', True))
        self.assertEqual(tunnel['streamSettings']['tlsSettings']['fingerprint'], 'chrome')
        self.assertEqual(tunnel['streamSettings']['sockopt']['dialerProxy'], 'http-upstream')
        self.assertEqual(normalized['outbounds'][1]['settings']['headers'], raw['outbounds'][1]['settings']['headers'])
        self.assertNotIn('wsSettings', tunnel['streamSettings'])
        self.assertEqual(normalized['dns']['servers'], raw['dns']['servers'])
        self.assertEqual(normalized['routing']['rules'][-1]['outboundTag'], tunnel['tag'])
        self.assertEqual(xray.normalize(normalized, True)[0], normalized)
        self.assertEqual(raw, original)

    def test_vless_replacement_preserves_assignments_and_revokes_old_lease(self):
        connected = self.connect()
        replaced = xray.save(self.store, dict(self.data, config=self.vless_config(), allow_insecure=True), self.profile['id'])
        self.assertEqual(replaced['id'], self.profile['id'])
        self.assertGreater(replaced['version'], self.profile['version'])
        with self.assertRaises(Fault): self.beat(connected)
        xray.disconnect(self.store, self.auth['token'], {'lease': connected['lease']})
        replacement = self.connect()
        self.assertEqual(replacement['config']['outbounds'][0]['protocol'], 'vless')
        self.beat(replacement)
        self.assertNotIn('00000000-0000-4000-8000-000000000001', json.dumps(self.store.profiles()))

    def test_vless_rejects_invalid_or_ambiguous_credentials_and_transport(self):
        with self.assertRaises(Fault): xray.normalize(self.vless_config())
        for update in [{'id': 'invalid'}, {'id': 123}, {'flow': 'xtls-rprx-vision'}, {'encryption': 'invalid'}]:
            raw = self.vless_config()
            raw['outbounds'][0]['settings']['vnext'][0]['users'][0].update(update)
            with self.assertRaises(Fault): xray.normalize(raw, True)
        for field, value in [('vnext', []), ('vnext', [None])]:
            raw = self.vless_config(); raw['outbounds'][0]['settings'][field] = value
            with self.assertRaises(Fault): xray.normalize(raw, True)
        raw = self.vless_config(); raw['outbounds'].append(config()['outbounds'][0])
        with self.assertRaises(Fault): xray.normalize(raw, True)
        raw = self.vless_config(); raw['outbounds'][0]['streamSettings']['network'] = 'ws'
        with self.assertRaises(Fault): xray.normalize(raw, True)

    def test_doh_rejects_local_mode_and_arbitrary_urls(self):
        for value in ['https+local://dns.google/dns-query', 'https://evil.example/dns-query',
                      'https://dns.google/dns-query?file=/etc/passwd', 'file:///etc/passwd']:
            raw = self.vless_config(); raw['dns']['servers'] = [value]
            with self.assertRaises(Fault): xray.normalize(raw, True)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.clock=[1800000000]
        self.store=Store(Path(self.tmp.name)/'xray.sqlite3', lambda:self.clock[0])
        self.private,self.public=device()
        self.data={'name':'Imported test','carrier':'MTN','config':config(),'enabled':True}
        self.profile=xray.save(self.store,self.data)
        issued=self.store.issue({'label':'Test','kind':'trial','duration_seconds':60,'quota_bytes':1000,'profile_ids':[self.profile['id']]})
        self.account=issued['account']['id']
        self.auth=self.store.activate(dict(proof(self.store,self.private,self.public,'activate'),code=issued['code']))

    def tearDown(self): self.store.close(); self.tmp.cleanup()

    def connect(self):
        return xray.connect(self.store,self.auth['token'],dict(proof(self.store,self.private,self.public,'connect'),profile_id=self.profile['id']))

    def beat(self,result,up=10,down=20):
        return xray.heartbeat(self.store,self.auth['token'],{'lease':result['lease'],'up':up,'down':down})

    def test_normalization_removes_local_listeners_and_rebuilds_routes(self):
        normalized,*_=xray.normalize(config())
        self.assertEqual(normalized['inbounds'],[{'tag':'tun-inbound','protocol':'tun','settings':{'name':'tpp0','mtu':1400}}])
        self.assertEqual(normalized['outbounds'][0]['streamSettings']['sockopt']['dialerProxy'],'http-upstream')
        self.assertNotIn('proxySettings', normalized['outbounds'][0])
        self.assertEqual(normalized['routing']['rules'][1]['inboundTag'],['tun-inbound'])
        self.assertNotIn('api',normalized)

    def test_insecure_requires_explicit_import_option(self):
        with self.assertRaises(Fault): xray.normalize(config(True))
        normalized,*_=xray.normalize(config(True),True)
        self.assertTrue(normalized['outbounds'][0]['streamSettings']['tlsSettings']['allowInsecure'])

    def test_current_dialer_proxy_import_and_repeated_normalization_preserve_upstream(self):
        raw = config()
        old = raw['outbounds'][0].pop('proxySettings')
        raw['outbounds'][0]['streamSettings']['sockopt'] = {'dialerProxy': old['tag']}
        first = xray.normalize(raw)[0]
        self.assertEqual(xray.normalize(first)[0], first)
        self.assertEqual(first['outbounds'][0]['streamSettings']['sockopt']['dialerProxy'], 'http-upstream')
        upstream = next(o for o in first['outbounds'] if o['tag'] == 'http-upstream')
        self.assertEqual(upstream['settings']['headers']['Host'], 'vpn.example.com:443')
        self.assertNotIn('proxySettings', json.dumps(first))

    def test_legacy_stored_proxy_is_migrated_on_connect(self):
        with self.store.db() as db:
            row = db.execute('SELECT config FROM xray_profiles WHERE profile=?', (self.profile['id'],)).fetchone()
            old = json.loads(row['config'])
            old['outbounds'][0]['streamSettings'].pop('sockopt', None)
            old['outbounds'][0]['proxySettings'] = {'tag': 'http-upstream', 'transportLayer': True}
            db.execute('UPDATE xray_profiles SET config=? WHERE profile=?', (json.dumps(old), self.profile['id']))
        connected = self.connect()['config']
        self.assertNotIn('proxySettings', json.dumps(connected))
        self.assertEqual(connected['outbounds'][0]['streamSettings']['sockopt']['dialerProxy'], 'http-upstream')
        upstream = next(o for o in connected['outbounds'] if o['tag'] == 'http-upstream')
        self.assertEqual(upstream['settings']['servers'][0]['address'], '192.0.2.1')
        self.assertEqual(upstream['settings']['headers']['Host'], 'vpn.example.com:443')

    def test_conflicting_or_malformed_proxy_settings_are_rejected(self):
        raw = config(); raw['outbounds'][0]['streamSettings']['sockopt'] = {'dialerProxy': 'different'}
        with self.assertRaises(Fault): xray.normalize(raw)
        for bad in [None, [], 'invalid']:
            raw = config(); raw['outbounds'][0]['streamSettings']['sockopt'] = bad
            with self.assertRaises(Fault): xray.normalize(raw)

    def test_dns_resolvers_follow_tunnel_routes_without_mutating_import(self):
        raw = config()
        raw['dns']['servers'] = ['tcp+local://1.1.1.1', 'tcp://8.8.8.8', '9.9.9.9', 'tcp+local://2606:4700:4700::1111']
        original = json.loads(json.dumps(raw))
        normalized, *_ = xray.normalize(raw)
        self.assertEqual(normalized['dns']['servers'],
                         ['tcp://1.1.1.1', 'tcp://8.8.8.8', '9.9.9.9', 'tcp://2606:4700:4700::1111'])
        self.assertEqual(raw, original)
        self.assertEqual(normalized['dns']['tag'], 'dns-in')
        dns_rule = next(r for r in normalized['routing']['rules'] if 'dns-in' in r.get('inboundTag', []))
        self.assertEqual(dns_rule['outboundTag'], 'trojan')

    def test_existing_stored_import_dns_is_normalized_on_connect(self):
        with self.store.db() as db:
            row = db.execute('SELECT config FROM xray_profiles WHERE profile=?', (self.profile['id'],)).fetchone()
            old = json.loads(row['config'])
            old['dns']['servers'] = ['tcp+local://1.1.1.1']
            old['inbounds'][0]['settings'].pop('name', None)
            db.execute('UPDATE xray_profiles SET config=? WHERE profile=?', (json.dumps(old), self.profile['id']))
        connected = self.connect()
        self.assertEqual(connected['config']['dns']['servers'], ['tcp://1.1.1.1'])
        self.assertNotIn('tcp+local://', json.dumps(connected['config']))
        self.assertEqual(connected['config']['inbounds'][0]['settings']['name'], 'tpp0')

    def test_password_only_returned_after_signed_connection(self):
        self.assertNotIn('test-secret-only',json.dumps(self.store.profiles()))
        self.assertNotIn('test-secret-only',json.dumps(self.profile))
        connected=self.connect(); self.assertIn('test-secret-only',json.dumps(connected['config']))
        with self.assertRaises(Fault): xray.connect(self.store,self.auth['token'],{'profile_id':self.profile['id']})

    def test_usage_idempotent_and_monotonic(self):
        r=self.connect(); self.beat(r); self.beat(r)
        self.assertEqual(self.store.account(self.account)['used'],30)
        with self.assertRaises(Fault): self.beat(r,9,20)
        self.beat(r,100,200); self.assertEqual(self.store.account(self.account)['used'],300)

    def test_suspension_and_expiry_revoke_lease(self):
        r=self.connect(); self.store.update_account(self.account,{'suspended':True})
        with self.assertRaises(Fault): self.beat(r)
        self.store.update_account(self.account,{'suspended':False})
        self.clock[0]+=61
        with self.assertRaises(Fault): self.beat(r)

    def test_disable_import_revokes_without_exposing_password(self):
        r=self.connect(); p=xray.toggle(self.store,self.profile['id'],{'enabled':False})
        self.assertFalse(p['enabled']); self.assertNotIn('test-secret-only',json.dumps(p))
        with self.assertRaises(Fault): self.beat(r)

    def test_changed_profile_revokes_lease(self):
        r=self.connect(); xray.save(self.store,self.data,self.profile['id'])
        with self.assertRaises(Fault): self.beat(r)

    def test_exhausted_usage_persists_and_denies_reconnect(self):
        r=self.connect()
        with self.assertRaises(Fault): self.beat(r,500,500)
        self.assertEqual(self.store.account(self.account)['used'],1000)
        with self.assertRaises(Fault): self.connect()

    def test_stale_or_wrong_lease_rejected(self):
        r=self.connect()
        with self.assertRaises(Fault): self.beat({'lease':'wrong'})
        with self.assertRaises(Fault): self.beat({'lease':None})
        self.clock[0]+=30
        with self.assertRaises(Fault): self.beat(r)
        newer=self.connect(); self.assertNotEqual(newer['lease'],r['lease'])

    def test_old_disconnect_does_not_revoke_new_connection(self):
        old=self.connect(); self.clock[0]+=30; newer=self.connect()
        xray.disconnect(self.store,self.auth['token'],{'lease':old['lease']})
        self.assertTrue(self.beat(newer)['ok'])

    def test_plain_tpp_cannot_use_imported_profile(self):
        with self.assertRaises(Fault):
            self.store.connect(self.auth['token'],dict(proof(self.store,self.private,self.public,'connect'),profile_id=self.profile['id']))

    def test_duplicate_live_session_rejected(self):
        self.connect()
        with self.assertRaises(Fault): self.connect()

    def test_unsafe_headers_paths_and_protocols_rejected(self):
        bad=config();bad['outbounds'][1]['settings']['headers']['Host']='test\r\nInjected: yes'
        with self.assertRaises(Fault): xray.normalize(bad)
        bad=config();bad['dns']['servers']=['/etc/passwd']
        with self.assertRaises(Fault): xray.normalize(bad)
        bad=config();bad['outbounds'][0]['protocol']='vless'
        with self.assertRaises(Fault): xray.normalize(bad)

    def test_restart_preserves_import(self):
        self.store.close();self.store=Store(Path(self.tmp.name)/'xray.sqlite3',lambda:self.clock[0])
        self.assertEqual(self.store.get_profile(self.profile['id'])['engine'],'xray')


class XrayApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_api.ApiTests.asyncSetUp
    asyncTearDown = test_api.ApiTests.asyncTearDown
    login = test_api.ApiTests.login
    async def test_import_requires_admin_and_protects_old_clients(self):
        data={'name':'Imported','carrier':'MTN','config':config(),'enabled':True}
        r=await self.client.post('/admin/api/xray-profiles',headers=self.headers,json=data);self.assertEqual(r.status,401)
        await self.login()
        r=await self.client.post('/admin/api/xray-profiles',headers=self.headers,json=data);self.assertEqual(r.status,200);p=await r.json()
        r=await self.client.get('/admin/api/state');self.assertNotIn('test-secret-only',await r.text())
        issued=self.store.issue({'label':'Test','kind':'trial','duration_seconds':60,'quota_bytes':1000,'profile_ids':[p['id']]})
        private,public=device();auth=self.store.activate(dict(proof(self.store,private,public,'activate'),code=issued['code']))
        headers={'Authorization':'Bearer '+auth['token']}
        r=await self.client.get('/v1/profiles',headers=headers);self.assertEqual((await r.json())['profiles'],[])
        headers['X-TPP-Engines']='tpp,xray'
        r=await self.client.get('/v1/profiles',headers=headers);self.assertEqual(len((await r.json())['profiles']),1)
        r=await self.client.post('/v1/connect',headers=headers,json=dict(proof(self.store,private,public,'connect'),profile_id=p['id']))
        self.assertEqual(r.status,200); connected=await r.json();self.assertEqual(connected['engine'],'xray')
        r=await self.client.post('/v1/xray/heartbeat',headers=headers,json={'lease':connected['lease'],'up':4,'down':8});self.assertEqual(r.status,200)
        r=await self.client.post('/v1/disconnect',headers=headers,json={});self.assertEqual(r.status,200)
        with self.assertRaises(Fault): xray.heartbeat(self.store,auth['token'],{'lease':connected['lease'],'up':4,'down':8})


    async def test_legacy_test_tls_requires_compatible_app_before_issuing_lease(self):
        await self.login()
        r=await self.client.post('/admin/api/xray-profiles',headers=self.headers,json={
            'name':'Supplier test','carrier':'MTN','config':config(True),'allow_insecure':True,'enabled':True})
        self.assertEqual(r.status,200);p=await r.json()
        issued=self.store.issue({'label':'Test','kind':'trial','duration_seconds':60,'quota_bytes':1000,'profile_ids':[p['id']]})
        private,public=device();auth=self.store.activate(dict(proof(self.store,private,public,'activate'),code=issued['code']))
        headers={'Authorization':'Bearer '+auth['token'],'X-TPP-Engines':'xray'}
        data=dict(proof(self.store,private,public,'connect'),profile_id=p['id'])
        r=await self.client.post('/v1/connect',headers=headers,json=data);self.assertEqual(r.status,426)
        with self.store.db() as db:
            self.assertFalse(db.execute('SELECT 1 FROM xray_sessions WHERE account=?',(issued['account']['id'],)).fetchone())
        headers['X-TPP-Features']='legacy-tls-test-v1'
        r=await self.client.post('/v1/connect',headers=headers,json=data);self.assertEqual(r.status,200)
        self.assertTrue((await r.json())['config']['outbounds'][0]['streamSettings']['tlsSettings']['allowInsecure'])

