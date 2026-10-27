import argparse
import base64
import getpass
import os
import secrets
from pathlib import Path

from .store import Fault, Store, password_hash


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['create-admin', 'reset-admin', 'backup'])
    parser.add_argument('--db', default=os.environ.get('TPP_DB', 'data/tpp.sqlite3'))
    parser.add_argument('--username', default='admin')
    parser.add_argument('--mfa', action='store_true')
    parser.add_argument('--output', default='backup.sqlite3')
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    store = Store(args.db)
    if args.command == 'backup':
        import sqlite3
        with store.db() as source, sqlite3.connect(args.output) as target:
            source.backup(target)
        print('Backup saved. Protect it as confidential account data.')
        return
    password = getpass.getpass('New password (14+ characters): ')
    if password != getpass.getpass('Repeat password: '):
        raise Fault('Passwords do not match')
    if len(password) < 14:
        raise Fault('Password must have at least 14 characters')
    secret = base64.b32encode(secrets.token_bytes(20)).decode() if args.mfa else ''
    if args.command == 'create-admin':
        store.bootstrap(args.username, password, secret)
    else:
        with store.db() as db:
            if db.execute('UPDATE admins SET username=?,password=?,totp=? WHERE id=1', (args.username, password_hash(password), secret)).rowcount != 1:
                raise Fault('Create an admin first')
            db.execute('DELETE FROM admin_sessions')
            store.audit(db, 'admin_reset')
    if secret:
        print('Add this secret to your authenticator now; it will not be shown again: ' + secret)
    print('Admin configured. Never commit passwords or MFA secrets.')


if __name__ == '__main__':
    try:
        main()
    except Fault as error:
        raise SystemExit(error.message)
