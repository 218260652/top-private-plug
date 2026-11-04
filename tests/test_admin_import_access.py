import tempfile
import unittest
from pathlib import Path

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

from backend.app import create_app
from backend.store import Store


class AdminImportAccessTest(unittest.IsolatedAsyncioTestCase):
    async def test_import_issues_bound_code_and_rolls_back_invalid_access(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.db')
            password = 'local-test-password'
            store.bootstrap('admin', password)
            origin = 'http://127.0.0.1:8080'
            headers = {'Origin': origin, 'X-TPP-Request': '1'}
            app = create_app(store, public_origin=origin, secure_cookies=False)
            async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as client:
                login = await client.post('/admin/api/login', headers=headers,
                                          json={'username': 'admin', 'password': password})
                self.assertEqual(login.status, 200)
                payload = {
                    'name': 'Telkom trial', 'carrier': 'Telkom',
                    'config': {'outbounds': [{
                        'protocol': 'trojan',
                        'settings': {'servers': [{'address': 'vpn.example.com', 'port': 443,
                                                   'password': 'local-test-password'}]},
                        'streamSettings': {'network': 'tcp', 'security': 'tls'},
                    }]},
                    'access': {'kind': 'trial', 'duration_seconds': 86400, 'quota_bytes': 0},
                }
                endpoint = '/admin/api/xray-profiles/import-with-access'
                response = await client.post(endpoint, headers=headers, json=payload)
                self.assertEqual(response.status, 400)
                self.assertEqual(store.profiles(), [])
                self.assertEqual(store.accounts(), [])

                payload['access']['quota_bytes'] = 500_000_000
                response = await client.post(endpoint, headers=headers, json=payload)
                result = await response.json()
                self.assertEqual(response.status, 201, result)
                self.assertTrue(result['code'].startswith('TPP-'))
                account = result['account']
                self.assertEqual(account['profile_ids'], [result['profile']['id']])
                self.assertEqual(account['label'], payload['name'])
                self.assertEqual(account['status'], 'pending')
                self.assertEqual(account['device_limit'], 50)
                self.assertEqual(account['carrier'], 'Telkom')
                self.assertEqual(account['quota'], 500_000_000)
                self.assertEqual(account['duration'], 86400)
                self.assertIsNone(account['expires'])

                account_path = '/admin/api/accounts/' + account['id']
                for action, status in [('paused', 'paused'), ('enabled', 'pending'),
                                       ('suspended', 'suspended')]:
                    response = await client.patch(account_path, headers=headers,
                                                  json={'access_state': action})
                    self.assertEqual(response.status, 200)
                    self.assertEqual((await response.json())['status'], status)
                response = await client.delete(account_path, headers=headers)
                self.assertEqual(response.status, 200)
                self.assertEqual(store.accounts(), [])
