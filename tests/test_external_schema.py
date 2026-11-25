"""Externally migrated deployments must run without schema-creation privileges."""
import os
import unittest
from unittest.mock import patch, MagicMock
from backend import hosted

class ExternalSchemaTests(unittest.TestCase):
    def test_runtime_checks_tables_without_running_ddl(self):
        with patch.dict(os.environ, {'DATABASE_URL':'postgresql://example/db','TPP_MIGRATION_URL':'postgresql://example/db','TPP_EXTERNAL_SCHEMA':'1'}), patch.object(hosted,'Store') as store, patch.object(hosted.subprocess,'run') as regression, patch.object(hosted.os,'execv') as launch:
            hosted.main()
            store.assert_called_once_with('postgresql://example/db',initialize=False)
            queries=store.return_value.db.return_value.__enter__.return_value.execute.call_args_list
            self.assertEqual(len(queries),10)
            self.assertTrue(all(c.args[0].startswith('SELECT 1 FROM ') for c in queries))
            regression.assert_not_called()
            store.return_value.close.assert_called_once()
            launch.assert_called_once()
    def test_schema_failure_prevents_server_launch(self):
        with patch.dict(os.environ, {'DATABASE_URL':'postgresql://example/db','TPP_MIGRATION_URL':'postgresql://example/db','TPP_EXTERNAL_SCHEMA':'1'}), patch.object(hosted,'Store') as store, patch.object(hosted.os,'execv') as launch:
            store.return_value.db.return_value.__enter__.return_value.execute.side_effect=RuntimeError('Missing table')
            with self.assertRaises(RuntimeError):hosted.main()
            launch.assert_not_called()
            store.return_value.close.assert_called_once()
