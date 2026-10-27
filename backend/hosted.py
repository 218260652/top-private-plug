"""Hosted admin/API entrypoint. Database credentials remain in environment only."""
import os
import subprocess
import sys

from .store import Store


def main():
    dsn = os.environ.get('DATABASE_URL', '')
    direct = os.environ.get('TPP_MIGRATION_URL', '')
    if not dsn.startswith(('postgres://', 'postgresql://')) or not direct.startswith(('postgres://', 'postgresql://')):
        raise SystemExit('Configure DATABASE_URL and TPP_MIGRATION_URL as secret PostgreSQL connection strings')
    # Test mutations in a unique isolated schema before applying new schema to public.
    subprocess.run([sys.executable, 'tools/verify_postgres.py', '--from-env'], check=True)
    migration = Store(direct)
    migration.close()
    os.environ['TPP_SKIP_SCHEMA_INIT'] = '1'
    os.execv(sys.executable, [sys.executable, '-m', 'backend.app'])


if __name__ == '__main__':
    main()
