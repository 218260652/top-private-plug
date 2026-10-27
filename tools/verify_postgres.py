"""Run entitlement regression tests in an isolated schema of a new test DB.

Credentials arrive on stdin and are not logged or written. Never run this
against a database without permission to create an isolated test schema.
"""
import json
import os
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
from backend.store import Store
from tests.test_control import ControlTests, device

dsn = (os.environ.get('TPP_MIGRATION_URL') or os.environ['DATABASE_URL']) if '--from-env' in sys.argv else json.loads(sys.stdin.readline())['dsn']
schema = 'tpp_test_' + uuid.uuid4().hex[:16]
with psycopg.connect(dsn, autocommit=True) as connection:
    connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))


class PostgresControlTests(ControlTests):
    def setUp(self):
        self.clock = [1_800_000_000]
        self.store = Store(dsn, lambda: self.clock[0], schema=schema)
        with self.store.db() as db:
            db.execute('TRUNCATE admins,admin_sessions,profiles,accounts,tokens,challenges,tickets,sessions,usage,audit RESTART IDENTITY CASCADE')
        self.private, self.public = device()
        self.profile = self.store.save_profile({'name':'MTN pilot','carrier':'MTN','server':'vpn.example.com','port':443,'sni':'vpn.example.com','tls_min':'1.2','enabled':True})

    def tearDown(self):
        self.store.close()


try:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PostgresControlTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
finally:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
sys.exit(0 if result.wasSuccessful() else 1)
