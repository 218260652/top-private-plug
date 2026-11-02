import json
import unittest
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch
from tests import test_xray


class UsageRefreshTests(unittest.TestCase):
    setUp = test_xray.XrayTests.setUp
    tearDown = test_xray.XrayTests.tearDown
    connect = test_xray.XrayTests.connect
    beat = test_xray.XrayTests.beat

    def test_active_trial_decimal_totals_and_ten_gb_balance(self):
        self.store.update_account(self.account, {'quota_bytes': 100_000_000_000})
        connected = self.connect()
        self.beat(connected, 1_000_000_000, 9_000_000_000)
        original_db = self.store.db

        class AggregateCursor:
            def __init__(self, cursor): self.cursor = cursor
            def fetchone(self):
                row = dict(self.cursor.fetchone())
                row['up'], row['down'] = Decimal(row['up']), Decimal(row['down'])
                return row

        class PgTypes:
            def __init__(self, db): self.db = db
            def execute(self, sql, values=()):
                cursor = self.db.execute(sql, values)
                return AggregateCursor(cursor) if 'SUM(up)' in sql else cursor

        @contextmanager
        def pg_types():
            with original_db() as db: yield PgTypes(db)

        with patch.object(self.store, 'db', pg_types):
            result = json.loads(json.dumps(self.store.account(self.account)))
        self.assertEqual(result['used'], 10_000_000_000)
        self.assertEqual(result['remaining_bytes'], 90_000_000_000)
        self.assertEqual(result['session']['down'], 9_000_000_000)
        self.beat(connected, 1_000_000_000, 9_000_000_000)
        self.assertEqual(self.store.account(self.account)['used'], 10_000_000_000)
