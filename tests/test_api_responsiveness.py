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
