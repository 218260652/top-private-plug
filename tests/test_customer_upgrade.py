import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import AioHTTPTestCase

from backend.app import create_app
from backend.customer import Customers, migrate, provision_staging_networks
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

    def test_login_allows_network_selection_before_any_password_change(self):
        self.assert_fault(401, lambda: self.login(password='incorrect'))
        self.assert_fault(401, lambda: self.login(username='unknown'))
        session = self.login()
        self.assertEqual(session['account']['must_change'],0)
        self.assertNotIn('password',session['account'])
        self.assertNotIn('notes',session['account'])
        self.assertEqual([p['carrier'] for p in self.call('networks',session)['networks']],['MTN','Telkom','Cell C'])
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
        self.assert_fault(400,lambda: self.service.admin('network','owner',{'carrier':'Cell C','profile':profile['id']}))
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

    def test_pending_connection_can_be_retried_but_live_connection_cannot(self):
        provision_staging_networks(self.store, json.dumps({'MTN':vless(), 'Telkom':vless()}))
        session = self.login()

        def connect(carrier):
            return self.call('connect', session, {**self.signed('connect'), 'carrier':carrier})

        first = connect('MTN')
        second = connect('Telkom')
        self.assertNotEqual(first['lease'], second['lease'])
        self.assert_fault(403, lambda: self.call('heartbeat', session, {'lease':first['lease']}))
        self.call('disconnect', session, {'lease':first['lease']})
        self.assertTrue(self.call('heartbeat', session, {'lease':second['lease']})['ok'])
        self.assert_fault(409, lambda: connect('MTN'))

    def test_staging_profiles_seed_missing_networks_without_overwriting(self):
        raw = json.dumps({'MTN':vless(), 'Telkom':vless()})
        provision_staging_networks(self.store, raw)
        with self.store.db() as db:
            first = self.service.network_rows(db)
        provision_staging_networks(self.store, raw)
        with self.store.db() as db:
            self.assertEqual(first, self.service.network_rows(db))
        self.assertEqual([(p['carrier'], p['enabled'], p['tested']) for p in first],
                         [('MTN', 1, 0), ('Telkom', 1, 0)])
        result = self.call('connect', self.login(), {**self.signed('connect'), 'carrier':'Telkom'})
        self.assertEqual(result['config']['outbounds'][0]['protocol'], 'vless')

    def test_paid_and_trial_device_limits(self):
        paid = self.service.admin('user', 'owner', {}, self.user)['user']
        self.assertEqual((paid['account_type'], paid['device_limit']), ('paid', 1))
        self.login()
        self.assert_fault(409, lambda: self.login(device=device()))
        self.assert_fault(400, lambda: self.service.admin('update', 'owner', {'device_limit':50}, self.user))

        trial = self.service.admin('create', 'owner', {'username':'trial-user','password':INITIAL,
                                                      'days':1,'account_type':'trial'})['id']
        with self.store.db() as db:
            for i in range(49):
                db.execute('INSERT INTO customer_devices VALUES(?,?,?,?,?,0)',
                           (f'device-{i}', trial, f'fixture-key-{i}', self.now, self.now))
        result = self.login(username='trial-user')
        self.assertEqual((result['account']['account_type'], result['account']['device_limit']), ('trial', 50))
        self.assert_fault(409, lambda: self.login(username='trial-user', device=device()))

    def test_direct_staging_update_replaces_only_managed_proxy_profiles(self):
        raw = vless()
        raw['outbounds'][0]['proxySettings'] = {'tag':'upstream'}
        raw['outbounds'].append({'tag':'upstream', 'protocol':'http', 'settings':{
            'servers':[{'address':'proxy.example.com','port':8080}]}})
        payload = json.dumps({'MTN':raw,'Telkom':raw,'Cell C':vless()})
        provision_staging_networks(self.store, payload)
        provision_staging_networks(self.store, payload, direct_mtn_telkom=True)
        provision_staging_networks(self.store, payload, direct_mtn_telkom=True)
        with self.store.db() as db:
            rows = {row['carrier']:row for row in self.service.network_rows(db)}
            for carrier in ('MTN','Telkom'):
                self.assertEqual(rows[carrier]['version'], 2)
                config = self.service.connection_config(db, rows[carrier])
                self.assertNotIn('sockopt', config['outbounds'][0]['streamSettings'])
                self.assertNotIn('http', [outbound['protocol'] for outbound in config['outbounds']])
            self.assertEqual(rows['Cell C']['version'], 1)

    def test_login_bootstrap_excludes_cell_c_and_does_not_allocate_leases(self):
        provision_staging_networks(self.store, json.dumps({carrier:vless() for carrier in ('MTN','Telkom','Cell C')}))
        session = self.login()
        with patch.dict(os.environ, {'TPP_CELL_C_CODE':'fixture-code'}):
            result = self.call('bootstrap', session, self.signed('connect'))
        self.assertEqual(set(result['profiles']), {'MTN','Telkom'})
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM customer_leases').fetchone()[0], 0)
        self.service.admin('lifecycle', 'owner', {'action':'pause'}, self.user)
        self.assert_fault(401, lambda: self.call('bootstrap', session))

    def test_cell_c_connection_requires_server_configured_code(self):
        profile = save(self.store, {'name':'Cell C fixture','carrier':'Cell C','config':vless()})
        self.service.admin('network','owner',{'carrier':'Cell C','profile':profile['id']})
        session = self.login()

        def connect(**values):
            return self.call('connect', session, {**self.signed('connect'), 'carrier':'Cell C', **values})

        with patch.dict(os.environ, {'TPP_CELL_C_CODE':''}):
            self.assert_fault(403, lambda: connect(carrier_code='fixture-code'))
        with patch.dict(os.environ, {'TPP_CELL_C_CODE':'fixture-code'}):
            self.assert_fault(403, connect)
            self.assert_fault(403, lambda: connect(carrier_code='wrong'))
            self.assertEqual(connect(carrier_code='fixture-code')['engine'], 'xray')

    def test_pause_renew_resume_suspend_and_delete(self):
        session = self.login()
        def action(name, **data):
            self.service.admin('lifecycle','owner',{'action':name,**data},self.user)
        def account():
            return self.service.admin('user','owner',{},self.user)['user']
        expires = account()['expires']
        action('pause')
        self.assertEqual(account()['status'],'paused')
        self.assert_fault(401,lambda: self.call('profile',session))
        self.assert_fault(403,self.login)
        action('renew',days=7)
        self.assertEqual(account()['expires'],expires+7*86400)
        self.assertEqual(account()['status'],'paused')
        action('resume')
        self.assertEqual(account()['status'],'active')
        action('suspend')
        self.assertEqual(account()['status'],'suspended')
        action('delete')
        self.assert_fault(404,account)
        self.assertEqual(self.service.admin('users','owner',{},query='example')['users'],[])
        audit = self.service.admin('overview','owner',{})['events']
        self.assertIn('customer_delete',{item['action'] for item in audit})

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
        self.assertIn('initial_password',await response.json())
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        response = await self.client.get('/admin/api/customers/users',cookies=cookie)
        self.assertEqual(response.status,200)
        self.assertNotIn('password',(await response.json())['users'][0])
