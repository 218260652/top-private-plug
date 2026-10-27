import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer

from backend.app import create_app
from backend.store import Store
from tests.test_control import device, proof
from backend.hosted import create_setup_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'api.sqlite3')
        self.store.bootstrap('admin','My long private password!')
        self.client=TestClient(TestServer(create_app(self.store, 'https://admin.test', False)))
        await self.client.start_server()
        self.headers={'Origin':'https://admin.test','X-TPP-Request':'1'}

    async def asyncTearDown(self):
        await self.client.close();self.tmp.cleanup()

    async def login(self):
        response=await self.client.post('/admin/api/login',headers=self.headers,json={'username':'admin','password':'My long private password!'})
        self.assertEqual(response.status,200);return response

    async def test_admin_authentication_required(self):
        response=await self.client.get('/admin/api/state');self.assertEqual(response.status,401)

    async def test_cross_origin_and_missing_origin_rejected(self):
        for headers in [{},{'Origin':'https://evil.test','X-TPP-Request':'1'},{'Origin':'https://admin.test'}]:
            r=await self.client.post('/admin/api/login',headers=headers,json={'username':'admin','password':'My long private password!'})
            self.assertEqual(r.status,403)

    async def test_session_cookie_http_only_and_strict(self):
        r=await self.login();cookie=r.headers.get('Set-Cookie','');self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        r=await self.client.get('/admin/api/state');self.assertEqual(r.status,200)
        r=await self.client.post('/admin/api/logout',headers=self.headers,json={});self.assertEqual(r.status,200)
        r=await self.client.get('/admin/api/state');self.assertEqual(r.status,401)

    async def test_full_admin_to_client_flow(self):
        await self.login()
        p=await self.client.post('/admin/api/profiles',headers=self.headers,json={'name':'Cell C','carrier':'Cell C','server':'vpn.example.com','port':8443,'sni':'vpn.example.com','tls_min':'1.2','enabled':True});self.assertEqual(p.status,200);profile=await p.json()
        r=await self.client.post('/admin/api/accounts',headers=self.headers,json={'label':'Client','kind':'trial','duration_seconds':10800,'quota_bytes':1_000_000_000,'profile_ids':[profile['id']]});self.assertEqual(r.status,201);issued=await r.json()
        private,public=device();challenge=await self.client.post('/v1/challenge',json={'public_key':public,'purpose':'activate'});self.assertEqual(challenge.status,200)
        # A fresh signed proof also exercises the identical public challenge store.
        r=await self.client.post('/v1/activate',json=dict(proof(self.store,private,public,'activate'),code=issued['code']));self.assertEqual(r.status,200);activation=await r.json()
        auth={'Authorization':'Bearer '+activation['token']}
        r=await self.client.get('/v1/status',headers=auth);data=await r.json();self.assertEqual(data['status'],'active');self.assertEqual(data['expires']-data['activated'],10800)
        r=await self.client.get('/v1/profiles',headers=auth);self.assertEqual(len((await r.json())['profiles']),1)
        r=await self.client.post('/v1/connect',headers=auth,json={});self.assertEqual(r.status,503)
        r=await self.client.patch('/admin/api/accounts/'+issued['account']['id'],headers=self.headers,json={'suspended':True});self.assertEqual(r.status,200)
        r=await self.client.get('/v1/status',headers=auth);self.assertEqual((await r.json())['status'],'suspended')
        r=await self.client.delete('/admin/api/accounts/'+issued['account']['id'],headers=self.headers);self.assertEqual(r.status,200)
        r=await self.client.get('/v1/status',headers=auth);self.assertEqual(r.status,401)

    async def test_login_rate_limit(self):
        for _ in range(5):
            r=await self.client.post('/admin/api/login',headers=self.headers,json={'username':'admin','password':'wrong'});self.assertEqual(r.status,401)
        r=await self.client.post('/admin/api/login',headers=self.headers,json={'username':'admin','password':'wrong'});self.assertEqual(r.status,429)

    async def test_security_headers_and_ui_assets(self):
        for path in ['/admin/','/assets/admin.js','/assets/style.css','/assets/icon.svg']:
            r=await self.client.get(path);self.assertEqual(r.status,200);self.assertEqual(r.headers['X-Frame-Options'],'DENY');self.assertIn("script-src 'self'",r.headers['Content-Security-Policy'])

    async def test_client_cannot_access_admin(self):
        r=await self.client.get('/admin/api/state',headers={'Authorization':'Bearer guessed'});self.assertEqual(r.status,401)
        r=await self.client.get('/v1/status');self.assertEqual(r.status,401)

    async def test_bounded_request_body(self):
        r=await self.client.post('/v1/challenge',json={'public_key':'x'*20000,'purpose':'activate'});self.assertEqual(r.status,413)


class SetupOnlyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client=TestClient(TestServer(create_setup_app()));await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_setup_page_does_not_accept_secrets_or_accounts(self):
        r=await self.client.get('/');self.assertEqual(r.status,200);page=await r.text();self.assertNotIn('<form',page)
        for path in ['/admin/api/login','/admin/api/accounts','/v1/activate','/setup']:
            r=await self.client.post(path,json={'password':'attacker','code':'fake'});self.assertEqual(r.status,503)

    async def test_setup_status_clearly_not_operational(self):
        r=await self.client.get('/health');data=await r.json();self.assertFalse(data['admin_ready']);self.assertFalse(data['gateway_enabled']);self.assertEqual(data['status'],'setup_required')
