import os
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase

from backend.app import create_app
from backend.customer import Customers, migrate
from backend.store import Fault, Store
from backend.xray import save
from tests.test_control import device, proof

ORIGIN = 'https://top-private-plug-test-api.onrender.com'
INITIAL = 'Temporary password example'
REPLACEMENT = 'A different password for the fixture'


def vless():
    return {'outbounds': [{'protocol':'vless', 'settings': {'vnext': [{
        'address':'vpn.example.com', 'port':443,
        'users':[{'id':'00000000-0000-4000-8000-000000000001','encryption':'none'}]}]},
        'streamSettings': {'network':'tcp','security':'tls',
                           'tlsSettings': {'serverName':'vpn.example.com'}}}]}


class CustomerStoreCases:
    def setUp(self):
        self.now = 1_800_000_000
        self.store = self.open_store()
        self.addCleanup(self.store.close)
        migrate(self.store)
        migrate(self.store)
        self.service = Customers(self.store)
        self.user = self.service.admin('create','owner',{'username':'Example','password':INITIAL,
                                                        'days':1,'device_limit':1})['id']
        self.key, self.public = device()

    def signed(self, purpose, key=None, public=None):
        if key is None:
            key, public = self.key,self.public
        return proof(self.store,key,public,'customer-'+purpose)

    def login(self, **kwargs):
        key, public = kwargs.pop('device', (self.key,self.public))
        return self.service.login({**self.signed('login',key,public),'public_key':public,
                                  'username':'example','password':INITIAL,**kwargs},'source')

    def call(self, op, tokens, data=None):
        return self.service.customer(op,tokens['access_token'],data or {})

    def assert_fault(self, status, action):
        with self.assertRaises(Fault) as caught:
            action()
        self.assertEqual(caught.exception.status,status)

    def test_login_first_password_device_limit_and_logout(self):
        self.assert_fault(401, lambda: self.login(password='incorrect'))
        self.assert_fault(401, lambda: self.login(username='unknown'))
        session = self.login()
        self.assertEqual(session['account']['must_change'],1)
        self.assertNotIn('password',session['account'])
        self.assert_fault(403,lambda: self.call('networks',session))
        updated = self.call('password',session,{**self.signed('password'),'password':REPLACEMENT})
        self.assert_fault(401,lambda: self.call('profile',session))
        self.assert_fault(409,lambda: self.login(device=device(),password=REPLACEMENT))
        self.assertEqual(len(self.call('networks',updated)['networks']),3)
        self.call('logout',updated)
        self.assert_fault(401,lambda: self.call('profile',updated))

    def test_refresh_expires_and_replay_revokes_family(self):
        session = self.login()
        self.now += 301
        self.assert_fault(401,lambda: self.call('profile',session))
        refreshed = self.service.refresh({**self.signed('refresh'),'refresh_token':session['refresh_token']})
        self.assertNotEqual(session['refresh_token'],refreshed['refresh_token'])
        self.assert_fault(401,lambda: self.service.refresh(
            {**self.signed('refresh'),'refresh_token':session['refresh_token']}))
        self.assert_fault(401,lambda: self.call('profile',refreshed))

    def test_subscription_device_revocation_and_admin_reset(self):
        session = self.login()
        self.service.admin('update','owner',{'state':'suspended'},self.user)
        self.assert_fault(401,lambda: self.call('profile',session))
        self.assert_fault(403,self.login)
        self.service.admin('update','owner',{'state':'active'},self.user)
        self.now += 86401
        self.assert_fault(403,self.login)
        self.service.admin('update','owner',{'expires':self.now+86400},self.user)
        session = self.login()
        entry = self.service.admin('user','owner',{},self.user)['devices'][0]
        self.service.admin('revoke-device','owner',{'device':entry['id']},self.user)
        self.assert_fault(401,lambda: self.call('profile',session))
        self.assert_fault(403,self.login)
        new_password = self.service.admin('reset','owner',{},self.user)['temporary_password']
        self.assert_fault(401,self.login)
        fresh = self.login(device=device(),password=new_password)
        self.service.admin('update','owner',{'state':'revoked'},self.user)
        self.assert_fault(401,lambda: self.call('profile',fresh))
        self.assert_fault(409,lambda: self.service.admin('update','owner',{'state':'active'},self.user))
        detail = self.service.admin('user','owner',{},self.user)
        self.assertIn('device_revoked',{entry['action'] for entry in detail['events']})
        self.assertNotIn('password',detail['user'])

    def test_real_vless_configuration_delivery_and_lease_expiry(self):
        profile = save(self.store,{'name':'VLESS fixture','carrier':'MTN','config':vless()})
        self.service.admin('network','owner',{'carrier':'MTN','profile':profile['id']})
        session = self.login()
        session = self.call('password',session,{**self.signed('password'),'password':REPLACEMENT})
        self.assert_fault(403,lambda: self.call('connect',session,{**self.signed('connect'),'carrier':'Telkom'}))
        self.service.admin('update','owner',{'expires':self.now+12},self.user)
        result = self.call('connect',session,{**self.signed('connect'),'carrier':'MTN'})
        self.assertEqual(result['config']['outbounds'][0]['protocol'],'vless')
        self.assertEqual(result['lease_seconds'],12)
        self.now += 10
        self.assertEqual(self.call('heartbeat',session,{'lease':result['lease']})['lease_seconds'],2)
        self.now += 2
        self.assert_fault(403,lambda: self.call('heartbeat',session,{'lease':result['lease']}))
        self.assert_fault(403,lambda: self.call('connect',session,{**self.signed('connect'),'carrier':'MTN'}))

    def test_limit_and_parameterized_search(self):
        for _ in range(8):
            self.assert_fault(401,lambda: self.login(password='wrong'))
        self.assert_fault(429,self.login)
        self.assertEqual(self.service.admin('users','owner',{},query="' OR 1=1 --")['users'],[])
        self.assertEqual(self.service.admin('users','owner',{},query='EXAMP')['users'][0]['id'],self.user)


class SQLiteCustomerTests(CustomerStoreCases,unittest.TestCase):
    def open_store(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Store(str(Path(directory.name)/'accounts.sqlite3'),clock=lambda:self.now)


@unittest.skipUnless(os.environ.get('TPP_TEST_POSTGRES'),'isolated PostgreSQL test URL required')
class PostgresCustomerTests(CustomerStoreCases,unittest.TestCase):
    def open_store(self):
        from uuid import uuid4
        from psycopg import connect
        from psycopg.sql import Identifier, SQL
        dsn = os.environ['TPP_TEST_POSTGRES']
        schema = 'customer_test_' + uuid4().hex
        with connect(dsn,autocommit=True) as conn:
            conn.execute(SQL('CREATE SCHEMA {}').format(Identifier(schema)))
        def cleanup():
            with connect(dsn,autocommit=True) as conn:
                conn.execute(SQL('DROP SCHEMA {} CASCADE').format(Identifier(schema)))
        self.addCleanup(cleanup)
        return Store(dsn,clock=lambda:self.now,schema=schema)


class CustomerAdminApiTests(AioHTTPTestCase):
    async def get_application(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(str(Path(directory.name)/'accounts.sqlite3'))
        self.store.bootstrap('test-admin','Fixture admin password only')
        migrate(self.store)
        return create_app(self.store,public_origin=ORIGIN,secure_cookies=False,customers_enabled=True)

    async def test_admin_authorization_origin_and_no_hash_in_response(self):
        endpoint = '/admin/api/customers/create'
        data = {'username':'customer','days':30,'device_limit':2}
        headers = {'Origin':ORIGIN,'X-TPP-Request':'1'}
        response = await self.client.post(endpoint,json=data,headers=headers)
        self.assertEqual(response.status,401)
        response = await self.client.post('/admin/api/login',headers=headers,
                                          json={'username':'test-admin','password':'Fixture admin password only'})
        self.assertEqual(response.status,200)
        cookie = {'tpp_admin':response.cookies['tpp_admin'].value}
        response = await self.client.post(endpoint,json=data,cookies=cookie)
        self.assertEqual(response.status,403)
        response = await self.client.post(endpoint,json=data,cookies=cookie,headers=headers)
        self.assertEqual(response.status,200)
        self.assertIn('temporary_password',await response.json())
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        response = await self.client.get('/admin/api/customers/users',cookies=cookie)
        self.assertEqual(response.status,200)
        self.assertNotIn('password',(await response.json())['users'][0])
