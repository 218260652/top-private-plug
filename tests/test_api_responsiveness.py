"""A deliberately blocked DB request must not block the HTTP event loop."""
import asyncio
import threading
import time
import unittest
from unittest.mock import patch
from tests import test_api as api_cases


class ResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api_cases.ApiTests.asyncSetUp
    asyncTearDown = api_cases.ApiTests.asyncTearDown
    async def test_slow_database_does_not_block_health(self):
        entered, release = threading.Event(), threading.Event()
        def slow_auth(token):
            entered.set()
            release.wait(5)
            return {'id': 'test-only'}
        response_task = None
        try:
            with patch.object(self.store, 'client_auth', side_effect=slow_auth), \
                 patch.object(self.store, 'account', return_value={'status': 'active'}):
                start = time.monotonic()
                response_task = asyncio.create_task(self.client.get('/v1/status', headers={'Authorization': 'Bearer fixture'}))
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                health = await self.client.get('/health')
                self.assertEqual(health.status, 200)
                self.assertLess(time.monotonic() - start, 3, 'Database call stalled the web event loop')
                release.set()
                self.assertEqual((await response_task).status, 200)
        finally:
            release.set()
            if response_task is not None:
                await response_task


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def check_startup(self, existing):
        import os
        from unittest.mock import AsyncMock, MagicMock, mock_open
        from backend import app
        class ReadyToServe(Exception): pass
        store = MagicMock()
        store.has_admin.return_value = existing
        runner = MagicMock()
        runner.setup = AsyncMock(side_effect=ReadyToServe)
        environment = {'TPP_LOCAL_DEV': '1', 'TPP_PUBLIC_ORIGIN': 'http://127.0.0.1:8080',
                       'TPP_DB': 'fixture-only.sqlite3', 'TPP_BOOTSTRAP_PASSWORD': 'fixture-only-password'}
        with patch.dict(os.environ, environment, clear=True), \
             patch.object(app.os, 'umask'), patch.object(app.fcntl, 'flock'), \
             patch('backend.app.open', mock_open()), patch.object(app, 'Store', return_value=store), \
             patch.object(app, 'create_app', return_value=object()), \
             patch.object(app.web, 'AppRunner', return_value=runner):
            with self.assertRaises(ReadyToServe):
                await app.main()
        store.has_admin.assert_called_once_with()
        if existing: store.bootstrap.assert_not_called()
        else: store.bootstrap.assert_called_once_with('admin', 'fixture-only-password')

    async def test_existing_admin_startup_with_bootstrap_setting(self):
        await self.check_startup(True)

    async def test_first_admin_bootstrap_startup(self):
        await self.check_startup(False)
