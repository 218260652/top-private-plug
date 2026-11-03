import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet

from backend import xray
from backend.app import create_app
from backend.profile_mail import ProfileMailer, DeliveryFailure
from backend.store import Store, Fault


def imported():
    return {'name': 'Owner test', 'carrier': 'MTN', 'config': {'outbounds': [{
        'protocol': 'vless', 'settings': {'vnext': [{'address': 'vpn.example.com', 'port': 443,
        'users': [{'id': 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', 'encryption': 'none'}]}]},
        'streamSettings': {'network': 'ws', 'security': 'tls', 'tlsSettings': {
        'serverName': 'vpn.example.com', 'fingerprint': 'chrome'}, 'wsSettings': {
        'path': '/private path', 'headers': {'Host': 'ws.example.com'}}}}]}}


class MailTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'mail.sqlite3'
        self.clock = [1800000000]
        self.store = self.open_store()
        self.key = Fernet.generate_key()
        self.mail = ProfileMailer(self.store, self.key, 'owner@example.com', 'sender@example.com', 'test-api-key')

    def open_store(self):
        return Store(self.path, lambda: self.clock[0], schema=getattr(self, 'schema', 'public'))

    async def asyncTearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def pending(self):
        with self.store.db() as db:
            return list(db.execute('SELECT * FROM profile_mail_outbox ORDER BY created,id'))

    def envelope(self, row):
        return json.loads(self.mail.cipher.decrypt(row['payload'].encode()))

    async def test_import_replace_export_full_payload_and_encryption(self):
        data = imported()
        profile = xray.save(self.store, data, notifier=self.mail)
        xray.save(self.store, data, profile['id'], notifier=self.mail)
        exported = xray.export_profile(self.store, profile['id'], notifier=self.mail)
        self.assertEqual(len(self.pending()), 3)
        actions = []
        for row in self.pending():
            self.assertNotIn('vpn.example.com', row['payload'])
            self.assertNotIn('aaaaaaaa-bbbb', row['payload'])
            envelope = self.envelope(row)
            self.assertEqual(envelope['to'], ['owner@example.com'])
            document = json.loads(envelope['text'].split('\n\n', 1)[1])
            actions.append(document['action'])
            self.assertEqual(document['profile']['config']['outbounds'][0]['settings']['vnext'][0]['users'][0]['id'],
                             'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee')
            self.assertIn('path=%2Fprivate+path', document['profile']['vless_uri'])
            self.assertIn('host=ws.example.com', document['profile']['vless_uri'])
            self.assertIn('fp=chrome', document['profile']['vless_uri'])
            if document['action'] == 'import':
                self.assertEqual(document['profile']['source_config'], data['config'])
        self.assertCountEqual(actions, ['import', 'import', 'export'])
        self.assertIn('vless://', exported['vless_uri'])
        self.assertEqual(exported['version'], 2)
        public = json.dumps(self.store.profiles())
        self.assertNotIn('aaaaaaaa-bbbb', public)
        self.assertNotIn('owner@example.com', public)

    async def test_invalid_import_export_and_rollback_do_not_queue(self):
        with self.assertRaises(Fault):
            xray.save(self.store, {'config': {}}, notifier=self.mail)
        with self.assertRaises(Fault):
            xray.export_profile(self.store, 'missing', notifier=self.mail)
        self.assertEqual(self.pending(), [])
        original = self.mail.enqueue
        def fail_after_queue(db, action, document):
            original(db, action, document)
            raise RuntimeError('test rollback')
        with patch.object(self.mail, 'enqueue', side_effect=fail_after_queue):
            with self.assertRaises(RuntimeError):
                xray.save(self.store, imported(), notifier=self.mail)
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.store.profiles(), [])

    async def test_restart_retries_without_secret_logs_then_removes_payload(self):
        xray.save(self.store, imported(), notifier=self.mail)
        self.store.close()
        self.store = self.open_store()
        self.mail = ProfileMailer(self.store, self.key, 'owner@example.com', 'sender@example.com', 'test-api-key')
        calls = []
        async def fail(session, event, envelope):
            calls.append(event)
            raise RuntimeError('test-api-key vpn.example.com aaaaaaaa-bbbb')
        with patch.object(self.mail, 'send', side_effect=fail), self.assertLogs('backend.profile_mail', 'WARNING') as logs:
            await self.mail.drain_once(None)
        self.assertNotIn('test-api-key', str(logs.output))
        self.assertNotIn('vpn.example.com', str(logs.output))
        self.assertEqual(self.pending()[0]['attempts'], 1)
        with patch.object(self.mail, 'send', side_effect=fail):
            await self.mail.drain_once(None)
        self.assertEqual(len(calls), 1)
        self.clock[0] += 31
        async def success(session, event, envelope): calls.append(event)
        with patch.object(self.mail, 'send', side_effect=success):
            await self.mail.drain_once(None)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(self.pending(), [])

    async def test_transport_fixed_endpoint_no_redirect_and_no_provider_echo(self):
        class Response:
            status = 200
            async def json(self): return {'id': 'mail-test'}
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        class Session:
            def post(self, url, **kwargs):
                self.url, self.kwargs = url, kwargs
                return Response()
        session = Session()
        await self.mail.send(session, 'stable-event', {'text': 'test fixture only'})
        self.assertEqual(session.url, 'https://api.resend.com/emails')
        self.assertFalse(session.kwargs['allow_redirects'])
        self.assertEqual(session.kwargs['headers']['Idempotency-Key'], 'tpp-profile/stable-event')
        Response.status = 429
        with self.assertRaises(DeliveryFailure):
            await self.mail.send(session, 'stable-event', {})

    async def test_server_configuration_is_opt_in_and_validated(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(ProfileMailer.from_env(self.store))
            os.environ['TPP_PROFILE_MAIL_ENABLED'] = '1'
            with self.assertRaises(ValueError): ProfileMailer.from_env(self.store)
        with self.assertRaises(ValueError):
            ProfileMailer(self.store, self.key, 'owner@example.com\nBcc: other@example.com', 'sender@example.com', 'key')


class MailApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'api.sqlite3')
        self.store.bootstrap('admin', 'My long private password!')
        self.mail = ProfileMailer(self.store, Fernet.generate_key(), 'owner@example.com', 'sender@example.com', 'test-api-key')
        async def disabled_worker(): await asyncio.Event().wait()
        self.worker = patch.object(self.mail, 'run', side_effect=disabled_worker)
        self.worker.start()
        self.client = TestClient(TestServer(create_app(self.store, 'https://admin.test', False, profile_notifier=self.mail)))
        await self.client.start_server()
        self.headers = {'Origin': 'https://admin.test', 'X-TPP-Request': '1'}

    async def asyncTearDown(self):
        await self.client.close()
        self.worker.stop()
        self.store.close()
        self.tmp.cleanup()

    async def test_admin_only_exports_and_unchanged_public_interface(self):
        r = await self.client.post('/admin/api/xray-profiles/missing/export', headers=self.headers, json={})
        self.assertEqual(r.status, 401)
        await self.client.post('/admin/api/login', headers=self.headers,
                               json={'username': 'admin', 'password': 'My long private password!'})
        r = await self.client.post('/admin/api/xray-profiles', headers=self.headers, json=imported())
        self.assertEqual(r.status, 200)
        profile = await r.json()
        path = '/admin/api/xray-profiles/' + profile['id'] + '/export'
        r = await self.client.post(path, json={})
        self.assertEqual(r.status, 403)
        r = await self.client.post(path, headers=self.headers, json={'recipient': 'attacker@example.com'})
        self.assertEqual(r.status, 400)
        r = await self.client.post(path, headers=self.headers, json={})
        self.assertEqual(r.status, 200)
        self.assertIn('attachment', r.headers['Content-Disposition'])
        self.assertEqual(r.headers['Cache-Control'], 'no-store')
        self.assertIn('vless_uri', await r.json())
        r = await self.client.get('/admin/api/state')
        public = await r.text()
        for secret in ['owner@example.com', 'test-api-key', 'aaaaaaaa-bbbb', 'profile_mail_outbox']:
            self.assertNotIn(secret, public)
        r = await self.client.get('/assets/admin.js')
        self.assertNotIn('profile_mail', await r.text())
        with self.store.db() as db:
            self.assertEqual(len(list(db.execute('SELECT * FROM profile_mail_outbox'))), 2)
