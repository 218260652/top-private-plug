"""Network grants are enforced before redemption and on authenticated requests."""
import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from backend.store import Store, Fault
from backend.app import create_app
from backend import xray
from tests.test_control import device, proof
from tests.test_api import imported_config

class NetworkBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'binding.sqlite3'
        self.store=self.new_store();self.private,self.public=device()
        self.profiles={n:xray.save(self.store,dict(name=n,carrier=n,config=imported_config(),enabled=True)) for n in Store.NETWORKS}
    def new_store(self):return Store(self.path)
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def issue(self,n,kind='paid',profile=None):
        return self.store.issue(dict(label='Network fixture',kind=kind,carrier=n,duration_seconds=3600,quota_bytes=1000000,profile_ids=[(profile or self.profiles[n])['id']]))
    def activate(self,item,n):
        return self.store.activate(dict(proof(self.store,self.private,self.public,'activate'),code=item['code'],carrier=n),require_network=True)
    def test_all_cross_network_pairs_reject_without_starting_or_binding(self):
        for kind in ['paid','trial']:
            for intended in Store.NETWORKS:
                item=self.issue(intended,kind)
                for wrong in Store.NETWORKS:
                    if wrong==intended:continue
                    with self.assertRaises(Fault) as error:self.activate(item,wrong)
                    self.assertEqual(error.exception.status,422)
                    account=self.store.account(item['account']['id'])
                    self.assertIsNone(account['activated']);self.assertIsNone(account['expires']);self.assertEqual(account['device_count'],0)
                good=self.activate(item,intended)
                old=self.store.account(item['account']['id'])
                with self.assertRaises(Fault):self.activate(item,next(n for n in Store.NETWORKS if n!=intended))
                self.assertEqual(self.store.client_auth(good['token'])['id'],old['id'])
                self.assertEqual(self.store.account(old['id'])['expires'],old['expires'])
    def test_bound_tokens_cannot_omit_or_change_network(self):
        result=self.activate(self.issue('Cell C'),'Cell C')
        for network in [None,'','MTN','Telkom','Any']:
            with self.assertRaises(Fault):self.store.check_network(result['token'],network)
        self.assertEqual(self.store.check_network(result['token'],'Cell C')['carrier'],'Cell C')
    def test_any_profile_does_not_create_an_any_network_code(self):
        profile=xray.save(self.store,dict(name='Shared supplier',carrier='Any',config=imported_config(),enabled=True))
        item=self.issue('Cell C',profile=profile)
        with self.assertRaises(Fault):self.activate(item,'MTN')
        self.activate(item,'Cell C')
    def test_profile_and_account_networks_must_align(self):
        with self.assertRaises(Fault):self.issue('MTN',profile=self.profiles['Cell C'])
        item=self.issue('MTN');old=item['account']
        with self.assertRaises(Fault):self.store.update_account(old['id'],{'carrier':'Cell C'})
        changed=self.store.update_account(old['id'],{'carrier':'Cell C','profile_ids':[self.profiles['Cell C']['id']]})
        self.assertEqual(changed['carrier'],'Cell C');self.assertEqual(changed['quota'],old['quota']);self.assertEqual(changed['expires'],old['expires'])
    def test_legacy_migration_preserves_balances_times_and_tokens(self):
        item=self.issue('Telkom');activated=self.store.activate(dict(proof(self.store,self.private,self.public,'activate'),code=item['code']))
        before=self.store.account(item['account']['id'])
        with self.store.db() as db:db.execute('ALTER TABLE accounts DROP COLUMN carrier')
        self.store.close();self.store=self.new_store()
        after=self.store.account(before['id'])
        self.assertEqual(after['carrier'],'Telkom')
        for key in ['activated','expires','quota','used']:self.assertEqual(before[key],after[key])
        self.store.check_network(activated['token'],None)
    def test_unassigned_legacy_tokens_require_admin_binding_in_updated_clients(self):
        item=self.issue('MTN');activated=self.store.activate(dict(proof(self.store,self.private,self.public,'activate'),code=item['code']))
        with self.store.db() as db:db.execute("UPDATE accounts SET carrier='' WHERE id=?",(item['account']['id'],))
        self.store.check_network(activated['token'],None)  # existing older client
        with self.assertRaises(Fault):self.store.check_network(activated['token'],'MTN')
    def test_profile_relabel_cannot_expand_an_existing_grant(self):
        item=self.issue('Cell C');result=self.activate(item,'Cell C')
        xray.save(self.store,dict(name='Changed',carrier='MTN',config=imported_config(),enabled=True),self.profiles['Cell C']['id'])
        with self.assertRaises(Fault):xray.connect(self.store,result['token'],dict(proof(self.store,self.private,self.public,'connect'),profile_id=self.profiles['Cell C']['id']))

class NetworkBindingApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'api.sqlite3')
        self.client=TestClient(TestServer(create_app(self.store,'https://admin.test',False)));await self.client.start_server()
        self.private,self.public=device();p=xray.save(self.store,dict(name='Cell C',carrier='Any',config=imported_config(),enabled=True))
        self.item=self.store.issue(dict(label='API fixture',kind='trial',carrier='Cell C',duration_seconds=3600,quota_bytes=1000,profile_ids=[p['id']]))
    async def asyncTearDown(self):await self.client.close();self.store.close();self.tmp.cleanup()
    async def test_public_activation_requires_matching_network_then_all_routes_enforce_it(self):
        health=await self.client.get('/health');self.assertEqual((await health.json())['network_binding_version'],1)
        for network in [None,'MTN','Telkom']:
            data=dict(proof(self.store,self.private,self.public,'activate'),code=self.item['code'])
            if network is not None:data['carrier']=network
            r=await self.client.post('/v1/activate',json=data);self.assertEqual(r.status,422)
        r=await self.client.post('/v1/activate',json=dict(proof(self.store,self.private,self.public,'activate'),code=self.item['code'],carrier='Cell C'));self.assertEqual(r.status,200);token=(await r.json())['token']
        for network in [None,'MTN','Telkom']:
            headers={'Authorization':'Bearer '+token}
            if network is not None:headers['X-TPP-Network']=network
            for path in ['/v1/status','/v1/profiles','/v1/connect','/v1/xray/heartbeat','/v1/xray/disconnect']:
                r=await (self.client.get(path,headers=headers) if path in ['/v1/status','/v1/profiles'] else self.client.post(path,headers=headers,json={}))
                self.assertEqual(r.status,422,(network,path,await r.text()))
        r=await self.client.get('/v1/profiles',headers={'Authorization':'Bearer '+token,'X-TPP-Network':'Cell C','X-TPP-Engines':'xray'})
        self.assertEqual(r.status,200);self.assertEqual(len((await r.json())['profiles']),1)
