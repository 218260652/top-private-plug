"""Durable single-node control plane. UTC seconds; quotas count IP bytes both ways."""
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


class Fault(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status
        super().__init__(message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def password_ok(password, encoded):
    return hmac.compare_digest(password_hash(password, encoded.split(':')[0]), encoded)


def totp_ok(secret, value, now):
    import struct
    if not secret:
        return True
    if not isinstance(value, str) or len(value) != 6 or not value.isdigit():
        return False
    key = base64.b32decode(secret)
    for offset in [-1, 0, 1]:
        mac = hmac.new(key, struct.pack('>Q', int(now // 30) + offset), hashlib.sha1).digest()
        start = mac[-1] & 15
        code = (int.from_bytes(mac[start:start + 4], 'big') & 0x7fffffff) % 1000000
        if hmac.compare_digest(str(code).zfill(6), value):
            return True
    return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
 password TEXT NOT NULL, totp TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS admin_sessions(hash TEXT PRIMARY KEY, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL, carrier TEXT NOT NULL,
 server TEXT NOT NULL, port INTEGER NOT NULL, sni TEXT NOT NULL, tls_min TEXT NOT NULL,
 enabled INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS xray_profiles(profile TEXT PRIMARY KEY REFERENCES profiles(id), config TEXT NOT NULL, insecure INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS xray_sessions(account TEXT PRIMARY KEY, profile TEXT NOT NULL, version INTEGER NOT NULL,
 lease TEXT NOT NULL, seen INTEGER NOT NULL, up INTEGER NOT NULL DEFAULT 0, down INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL,
 duration INTEGER NOT NULL, quota INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0,
 activated INTEGER, expires INTEGER, key TEXT, suspended INTEGER NOT NULL DEFAULT 0,
 deleted INTEGER NOT NULL DEFAULT 0, profiles TEXT NOT NULL, code_hash TEXT NOT NULL UNIQUE,
 created INTEGER NOT NULL, slot INTEGER);
CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id),
 expires INTEGER NOT NULL);
-- A trial is one account and one shared quota, with up to 50 distinct public keys.
-- Paid tokens and sessions retain their original single-device schema.
CREATE TABLE IF NOT EXISTS trial_devices(account TEXT NOT NULL REFERENCES accounts(id),
 device_key TEXT NOT NULL, PRIMARY KEY(account,device_key));
CREATE TABLE IF NOT EXISTS trial_tokens(hash TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id),
 device_key TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS trial_xray_sessions(account TEXT NOT NULL REFERENCES accounts(id),
 device_key TEXT NOT NULL, profile TEXT NOT NULL, version INTEGER NOT NULL,
 lease TEXT NOT NULL, seen INTEGER NOT NULL, up INTEGER NOT NULL DEFAULT 0, down INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(account,device_key));
CREATE TABLE IF NOT EXISTS challenges(id TEXT PRIMARY KEY, message TEXT NOT NULL, key TEXT NOT NULL,
 purpose TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS tickets(hash TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id),
 profile TEXT NOT NULL REFERENCES profiles(id), version INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id),
 profile TEXT NOT NULL REFERENCES profiles(id), version INTEGER NOT NULL, slot INTEGER UNIQUE NOT NULL,
 started INTEGER NOT NULL, seen INTEGER NOT NULL, up INTEGER NOT NULL DEFAULT 0, down INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_session_per_account ON sessions(account);
CREATE TABLE IF NOT EXISTS usage(id INTEGER PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id),
 at INTEGER NOT NULL, up INTEGER NOT NULL DEFAULT 0, down INTEGER NOT NULL DEFAULT 0,
 UNIQUE(account,at));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at INTEGER NOT NULL, action TEXT NOT NULL,
 subject TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
"""


class Store:
    def __init__(self, path, clock=time.time, schema='public', initialize=True):
        self.path, self.clock = str(path), clock
        self.postgres = None
        if self.path.startswith(('postgresql://', 'postgres://')):
            from .postgres import Database, schema_sql
            self.postgres = Database(self.path, schema)
            if not initialize:
                return
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.executescript(schema_sql(SCHEMA))
                db.execute('ALTER TABLE accounts ADD COLUMN IF NOT EXISTS slot BIGINT')
                db.execute('CREATE UNIQUE INDEX IF NOT EXISTS account_slot ON accounts(slot)')
                self._migrate_trial_devices(db)
            return
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            if 'slot' not in {r['name'] for r in db.execute('PRAGMA table_info(accounts)')}:
                db.execute('ALTER TABLE accounts ADD COLUMN slot INTEGER')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS account_slot ON accounts(slot)')
            self._migrate_trial_devices(db)

    @staticmethod
    def _migrate_trial_devices(db):
        """Idempotently carry forward activated trial keys, tokens and live leases."""
        db.execute("INSERT INTO trial_devices(account,device_key) SELECT id,key FROM accounts WHERE kind='trial' AND key IS NOT NULL ON CONFLICT(account,device_key) DO NOTHING")
        db.execute("INSERT INTO trial_tokens(hash,account,device_key,expires) SELECT t.hash,t.account,a.key,t.expires FROM tokens t JOIN accounts a ON a.id=t.account WHERE a.kind='trial' AND a.key IS NOT NULL ON CONFLICT(hash) DO NOTHING")
        db.execute("DELETE FROM tokens WHERE account IN (SELECT id FROM accounts WHERE kind='trial' AND key IS NOT NULL)")
        db.execute("INSERT INTO trial_xray_sessions(account,device_key,profile,version,lease,seen,up,down) SELECT x.account,a.key,x.profile,x.version,x.lease,x.seen,x.up,x.down FROM xray_sessions x JOIN accounts a ON a.id=x.account WHERE a.kind='trial' AND a.key IS NOT NULL ON CONFLICT(account,device_key) DO NOTHING")
        db.execute("DELETE FROM xray_sessions WHERE account IN (SELECT id FROM accounts WHERE kind='trial' AND key IS NOT NULL)")

    @contextmanager
    def db(self):
        if self.postgres:
            with self.postgres.connect() as db:
                yield db
            return
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def close(self):
        if self.postgres:
            self.postgres.close()

    def has_admin(self):
        with self.db() as db:
            return db.execute('SELECT 1 FROM admins WHERE id=1').fetchone() is not None

    def now(self):
        return int(self.clock())

    def audit(self, db, action, subject='', detail=''):
        db.execute('INSERT INTO audit(at,action,subject,detail) VALUES(?,?,?,?)',
                   (self.now(), action, subject, detail))

    def bootstrap(self, username, password, totp=''):
        if len(password) < 14:
            raise Fault('Use an admin password of at least 14 characters')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM admins').fetchone():
                raise Fault('Admin already exists; use the local reset-admin command')
            db.execute('INSERT INTO admins VALUES(1,?,?,?)', (username, password_hash(password), totp))
            self.audit(db, 'admin_created')

    def login(self, username, password, otp=''):
        with self.db() as db:
            admin = db.execute('SELECT * FROM admins WHERE id=1').fetchone()
            # Always perform a scrypt calculation, including unknown users.
            encoded = admin['password'] if admin else password_hash('unused-random-fallback')
            valid = password_ok(password, encoded)
            if not admin or not valid or not hmac.compare_digest(username, admin['username']) or not totp_ok(admin['totp'], otp, self.now()):
                raise Fault('Invalid sign-in details', 401)
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO admin_sessions VALUES(?,?)', (digest(token), self.now() + 28800))
            self.audit(db, 'admin_login')
            return token

    def admin_auth(self, token):
        with self.db() as db:
            if not db.execute('SELECT 1 FROM admin_sessions WHERE hash=? AND expires>?', (digest(token), self.now())).fetchone():
                raise Fault('Sign in to continue', 401)

    def logout(self, token):
        with self.db() as db:
            db.execute('DELETE FROM admin_sessions WHERE hash=?', (digest(token),))

    def save_profile(self, data, profile_id=None):
        import re
        fields = ['name', 'carrier', 'server', 'port', 'sni', 'tls_min', 'enabled']
        if set(data) - set(fields):
            raise Fault('Unknown profile field')
        if not all(k in data for k in fields):
            raise Fault('Complete all profile fields')
        if data['carrier'] not in ['MTN', 'Telkom', 'Cell C']:
            raise Fault('Choose MTN, Telkom or Cell C')
        for k in ['server', 'sni']:
            if not isinstance(data[k], str) or not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?', data[k]):
                raise Fault('Use a hostname or IPv4 address without a URL or path')
        if type(data['port']) is not int or not 1 <= data['port'] <= 65535:
            raise Fault('Port must be between 1 and 65535')
        if data['tls_min'] not in ['1.2', '1.3'] or type(data['enabled']) is not bool:
            raise Fault('TLS must be 1.2 or 1.3; enabled must be boolean')
        if not isinstance(data['name'], str) or not 1 <= len(data['name']) <= 80:
            raise Fault('Profile name must contain 1 to 80 characters')
        with self.db() as db:
            if profile_id:
                if db.execute('SELECT 1 FROM xray_profiles WHERE profile=?', (profile_id,)).fetchone():
                    raise Fault('Use the Xray import form to replace this profile')
                row = db.execute('SELECT * FROM profiles WHERE id=?', (profile_id,)).fetchone()
                if not row:
                    raise Fault('Profile not found', 404)
                db.execute('UPDATE profiles SET name=?,carrier=?,server=?,port=?,sni=?,tls_min=?,enabled=?,version=version+1 WHERE id=?',
                           tuple(data[k] for k in fields) + (profile_id,))
            else:
                profile_id = str(uuid.uuid4())
                db.execute('INSERT INTO profiles(id,name,carrier,server,port,sni,tls_min,enabled) VALUES(?,?,?,?,?,?,?,?)',
                           (profile_id,) + tuple(data[k] for k in fields))
            self.audit(db, 'profile_saved', profile_id)
        return self.get_profile(profile_id)

    def profiles(self):
        with self.db() as db:
            from .xray import metadata
            return metadata(db, [dict(r) for r in db.execute('SELECT * FROM profiles ORDER BY name')])

    def get_profile(self, profile_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM profiles WHERE id=?', (profile_id,)).fetchone()
            if not row:
                raise Fault('Profile not found', 404)
            from .xray import metadata
            return metadata(db, [dict(row)])[0]

    def issue(self, data):
        if not isinstance(data.get('label'), str) or not 1 <= len(data['label'].strip()) <= 100:
            raise Fault('Account label must contain 1 to 100 characters')
        if data.get('kind') not in ['trial', 'paid']:
            raise Fault('Choose trial or paid access')
        if type(data.get('duration_seconds')) is not int or not 60 <= data['duration_seconds'] <= 366 * 86400:
            raise Fault('Duration must be between 1 minute and 366 days')
        if type(data.get('quota_bytes')) is not int or not 1 <= data['quota_bytes'] <= 100_000_000_000_000:
            raise Fault('Set a positive data allowance in bytes')
        profiles = data.get('profile_ids')
        if not isinstance(profiles, list) or not 1 <= len(profiles) <= 20 or any(not isinstance(p, str) for p in profiles):
            raise Fault('Assign at least one connection profile')
        account_id, code = str(uuid.uuid4()), 'TPP-' + base64.b32encode(secrets.token_bytes(20)).decode()
        with self.db() as db:
            for profile in profiles:
                if not db.execute('SELECT 1 FROM profiles WHERE id=? AND enabled=1', (profile,)).fetchone():
                    raise Fault('Assigned profiles must exist and be enabled')
            db.execute('INSERT INTO accounts(id,label,kind,duration,quota,profiles,code_hash,created) VALUES(?,?,?,?,?,?,?,?)',
                       (account_id, data['label'].strip(), data['kind'], data['duration_seconds'], data['quota_bytes'], json.dumps(profiles), digest(code), self.now()))
            self.audit(db, 'code_created', account_id)
        return {'account': self.account(account_id), 'code': code}

    def view(self, row):
        r = dict(row)
        for k in ['key', 'code_hash', 'profiles', 'slot']:
            r.pop(k, None)
        r['device_limit'] = 50 if row['kind'] == 'trial' else 1
        r['device_count'] = int(r.get('device_count', 0)) if row['kind'] == 'trial' else int(row['key'] is not None)
        r['profile_ids'] = json.loads(row['profiles'])
        r['remaining_bytes'] = max(0, row['quota'] - row['used'])
        r['status'] = ('deleted' if row['deleted'] else 'suspended' if row['suspended'] else
                       'pending' if row['activated'] is None else 'expired' if row['expires'] <= self.now() else
                       'depleted' if row['used'] >= row['quota'] else 'active')
        r['server_time'] = self.now()
        seen = r.pop('last_seen', None)
        r['online'] = seen is not None and seen > self.now() - 10
        return r

    def account(self, account_id):
        with self.db() as db:
            row = db.execute('SELECT a.*, (SELECT COUNT(*) FROM trial_devices d WHERE d.account=a.id) AS device_count FROM accounts a WHERE a.id=?', (account_id,)).fetchone()
            if not row:
                raise Fault('Account not found', 404)
            result = self.view(row)
            session = db.execute('SELECT up,down,started,seen FROM sessions WHERE account=?', (account_id,)).fetchone()
            result['session'] = dict(session) if session and session['seen'] > self.now() - 10 else None
            if row['kind'] == 'trial':
                imported = db.execute('SELECT SUM(up) AS up,SUM(down) AS down,MAX(seen) AS seen,COUNT(*) AS connected_devices FROM trial_xray_sessions WHERE account=? AND seen>?', (account_id, self.now()-30)).fetchone()
                if imported['seen'] is None:
                    imported = None
            else:
                imported = db.execute('SELECT up,down,seen FROM xray_sessions WHERE account=? AND seen>?', (account_id, self.now()-30)).fetchone()
            if imported:
                result['session'] = dict(imported)
                result['session']['enforcement'] = 'app-reported'
            result['online'] = result['session'] is not None
            return result

    def accounts(self):
        with self.db() as db:
            return [self.view(r) for r in db.execute('SELECT a.*,COALESCE(t.seen,s.seen,x.seen) AS last_seen, (SELECT COUNT(*) FROM trial_devices d WHERE d.account=a.id) AS device_count FROM accounts a LEFT JOIN sessions s ON s.account=a.id LEFT JOIN xray_sessions x ON x.account=a.id LEFT JOIN (SELECT account,MAX(seen) AS seen FROM trial_xray_sessions GROUP BY account) t ON t.account=a.id WHERE a.deleted=0 ORDER BY a.created DESC')]

    @staticmethod
    def validate_key(key):
        try:
            decoded = base64.b64decode(key, validate=True)
            public = serialization.load_der_public_key(decoded)
            if not isinstance(public, ec.EllipticCurvePublicKey) or not isinstance(public.curve, ec.SECP256R1):
                raise ValueError()
            return public
        except Exception:
            raise Fault('A P-256 device public key is required') from None

    def challenge(self, key, purpose):
        self.validate_key(key)
        if purpose not in ['activate', 'connect']:
            raise Fault('Invalid challenge purpose')
        challenge_id = secrets.token_urlsafe(24)
        message = 'TPP/1:' + purpose + ':' + digest(key) + ':' + secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM challenges WHERE expires<=?', (self.now(),))
            db.execute('INSERT INTO challenges VALUES(?,?,?,?,?)', (challenge_id, message, key, purpose, self.now() + 60))
        return {'id': challenge_id, 'message': message}

    def proof(self, db, data, key, purpose):
        row = db.execute('SELECT * FROM challenges WHERE id=?', (data.get('challenge_id', ''),)).fetchone()
        if not row or row['expires'] <= self.now() or row['key'] != key or row['purpose'] != purpose:
            raise Fault('Challenge expired; try again', 401)
        try:
            self.validate_key(key).verify(base64.b64decode(data.get('signature', ''), validate=True), row['message'].encode(), ec.ECDSA(hashes.SHA256()))
        except Exception:
            raise Fault('Device verification failed', 401) from None
        db.execute('DELETE FROM challenges WHERE id=?', (row['id'],))

    def activate(self, data):
        code, key = data.get('code', ''), data.get('public_key', '')
        if not isinstance(code, str) or len(code) > 150:
            raise Fault('Invalid access code')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.proof(db, data, key, 'activate')
            row = db.execute('SELECT * FROM accounts WHERE code_hash=?', (digest(code.strip().upper()),)).fetchone()
            if not row or row['deleted'] or row['suspended']:
                raise Fault('Code is invalid or disabled', 403)
            if row['kind'] == 'trial':
                # The original trial clock and quota belong to the one account,
                # not to each device. Re-activation must not restart the clock.
                if row['activated'] is not None:
                    self.require_active(row)
                registered = db.execute('SELECT 1 FROM trial_devices WHERE account=? AND device_key=?', (row['id'], key)).fetchone()
                if not registered:
                    count = db.execute('SELECT COUNT(*) FROM trial_devices WHERE account=?', (row['id'],)).fetchone()[0]
                    if count >= 50:
                        raise Fault('Trial device limit reached (50 devices)', 409)
                    db.execute('INSERT INTO trial_devices(account,device_key) VALUES(?,?)', (row['id'], key))
                if row['activated'] is None:
                    db.execute('UPDATE accounts SET activated=?,expires=?,key=? WHERE id=?',
                               (self.now(), self.now() + row['duration'], key, row['id']))
                    self.audit(db, 'activated', row['id'])
                token = secrets.token_urlsafe(32)
                db.execute('DELETE FROM trial_tokens WHERE account=? AND device_key=?', (row['id'], key))
                db.execute('INSERT INTO trial_tokens(hash,account,device_key,expires) VALUES(?,?,?,?)',
                           (digest(token), row['id'], key, self.now() + 90 * 86400))
                if not registered:
                    self.audit(db, 'trial_device_added', row['id'])
            else:
                # Paid access stays strictly bound to one device and one token.
                if row['key'] and row['key'] != key:
                    raise Fault('Code is already linked to another device; contact support', 409)
                if row['activated'] is None:
                    db.execute('UPDATE accounts SET activated=?,expires=?,key=? WHERE id=?',
                               (self.now(), self.now() + row['duration'], key, row['id']))
                    self.audit(db, 'activated', row['id'])
                else:
                    self.require_active(row)
                    if row['key'] is None:
                        db.execute('UPDATE accounts SET key=? WHERE id=?', (key, row['id']))
                token = secrets.token_urlsafe(32)
                db.execute('DELETE FROM tokens WHERE account=?', (row['id'],))
                db.execute('INSERT INTO tokens VALUES(?,?,?)', (digest(token), row['id'], self.now() + 90 * 86400))
            account_id = row['id']
        return {'token': token, 'account': self.account(account_id)}

    def client_auth(self, token):
        with self.db() as db:
            row = db.execute('SELECT a.*,t.device_key AS auth_device_key FROM trial_tokens t JOIN accounts a ON a.id=t.account JOIN trial_devices d ON d.account=t.account AND d.device_key=t.device_key WHERE t.hash=? AND t.expires>?', (digest(token), self.now())).fetchone()
            if row:
                if row['deleted']:
                    raise Fault('Activate your access code', 401)
                return dict(row)
            row = db.execute('SELECT a.* FROM tokens t JOIN accounts a ON a.id=t.account WHERE t.hash=? AND t.expires>?', (digest(token), self.now())).fetchone()
            if not row or row['deleted']:
                raise Fault('Activate your access code', 401)
            # The single-device paid token keeps its original verification key.
            result = dict(row)
            result['auth_device_key'] = row['key']
            return result

    def require_active(self, row):
        if row['deleted'] or row['suspended']:
            raise Fault('Account disabled', 403)
        if row['activated'] is None or row['expires'] <= self.now():
            raise Fault('Access expired', 403)
        if row['used'] >= row['quota']:
            raise Fault('Data allowance exhausted', 403)

    def connect(self, token, data):
        account = self.client_auth(token)
        profile_id = data.get('profile_id', '')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM accounts WHERE id=?', (account['id'],)).fetchone()
            self.require_active(row)
            self.proof(db, data, account['auth_device_key'], 'connect')
            profile = db.execute('SELECT * FROM profiles WHERE id=? AND enabled=1', (profile_id,)).fetchone()
            if not profile or profile_id not in json.loads(row['profiles']):
                raise Fault('This connection profile is unavailable', 403)
            if db.execute('SELECT 1 FROM xray_profiles WHERE profile=?', (profile_id,)).fetchone():
                raise Fault('This profile requires the Xray engine')
            if db.execute('SELECT 1 FROM xray_sessions WHERE account=? AND seen>?', (row['id'], self.now()-30)).fetchone():
                raise Fault('Account already connected; disconnect first', 409)
            ticket = secrets.token_urlsafe(32)
            db.execute('DELETE FROM tickets WHERE expires<=? OR account=?', (self.now(), row['id']))
            db.execute('INSERT INTO tickets VALUES(?,?,?,?,?)', (digest(ticket), row['id'], profile_id, profile['version'], self.now() + 30))
        return {'ticket': ticket, 'profile': dict(profile)}

    def open_tunnel(self, ticket, sni, tls_version):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            t = db.execute('SELECT * FROM tickets WHERE hash=? AND expires>?', (digest(ticket), self.now())).fetchone()
            if not t:
                raise Fault('Tunnel ticket expired or invalid', 401)
            row = db.execute('SELECT * FROM accounts WHERE id=?', (t['account'],)).fetchone()
            self.require_active(row)
            p = db.execute('SELECT * FROM profiles WHERE id=?', (t['profile'],)).fetchone()
            if not p or not p['enabled'] or p['version'] != t['version'] or sni.lower() != p['sni'].lower():
                raise Fault('Profile changed; reconnect', 409)
            if p['tls_min'] == '1.3' and tls_version != 'TLSv1.3':
                raise Fault('This profile requires TLS 1.3', 403)
            if db.execute('SELECT 1 FROM sessions WHERE account=?', (row['id'],)).fetchone():
                raise Fault('Account already connected; disconnect first', 409)
            # Never reuse a private tunnel IP across accounts: stale kernel
            # conntrack/NAT entries must not send an old customer's replies to
            # a different customer after a disconnect or process restart.
            slots = {r[0] for r in db.execute('SELECT slot FROM accounts WHERE slot IS NOT NULL')}
            slot = row['slot'] if row['slot'] is not None else next((i for i in range(1, 16000) if i not in slots), None)
            if slot is None:
                raise Fault('Gateway capacity reached', 503)
            db.execute('UPDATE accounts SET slot=? WHERE id=?', (slot, row['id']))
            session_id = secrets.token_hex(16)
            db.execute('DELETE FROM tickets WHERE hash=?', (digest(ticket),))
            db.execute('INSERT INTO sessions(id,account,profile,version,slot,started,seen) VALUES(?,?,?,?,?,?,?)',
                       (session_id, row['id'], p['id'], p['version'], slot, self.now(), self.now()))
            self.audit(db, 'tunnel_opened', row['id'])
            return {'id': session_id, 'slot': slot, 'account': row['id']}

    def consume(self, session_id, size=0, direction='up'):
        if type(size) is not int or not 0 <= size <= 65535 or direction not in ['up', 'down']:
            raise Fault('Invalid packet accounting')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            session = db.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
            if not session:
                raise Fault('Session revoked', 403)
            row = db.execute('SELECT * FROM accounts WHERE id=?', (session['account'],)).fetchone()
            self.require_active(row)
            profile = db.execute('SELECT * FROM profiles WHERE id=?', (session['profile'],)).fetchone()
            if not profile or not profile['enabled'] or profile['version'] != session['version']:
                raise Fault('Profile updated; reconnect', 409)
            if row['used'] + size > row['quota']:
                raise Fault('Data allowance exhausted', 403)
            if size:
                db.execute('UPDATE accounts SET used=used+? WHERE id=?', (size, row['id']))
                # direction is selected from a fixed allowlist above, never request SQL.
                db.execute(f'UPDATE sessions SET {direction}={direction}+?,seen=? WHERE id=?', (size, self.now(), session_id))
                up, down = (size, 0) if direction == 'up' else (0, size)
                db.execute('INSERT INTO usage(account,at,up,down) VALUES(?,?,?,?) ON CONFLICT(account,at) DO UPDATE SET up=up+excluded.up,down=down+excluded.down',
                           (row['id'], self.now() // 60 * 60, up, down))
            else:
                db.execute('UPDATE sessions SET seen=? WHERE id=?', (self.now(), session_id))

    def close_tunnel(self, session_id):
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE id=?', (session_id,))

    def update_account(self, account_id, data):
        allowed = {'label', 'suspended', 'quota_bytes', 'duration_seconds', 'extend_seconds', 'reset_device'}
        if not data or set(data) - allowed:
            raise Fault('Unknown or empty account update')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM accounts WHERE id=? AND deleted=0', (account_id,)).fetchone()
            if not row:
                raise Fault('Account not found', 404)
            if 'label' in data:
                if not isinstance(data['label'], str) or not 1 <= len(data['label'].strip()) <= 100:
                    raise Fault('Invalid account label')
                db.execute('UPDATE accounts SET label=? WHERE id=?', (data['label'].strip(), account_id))
            if 'suspended' in data:
                if type(data['suspended']) is not bool:
                    raise Fault('Suspended must be boolean')
                db.execute('UPDATE accounts SET suspended=? WHERE id=?', (data['suspended'], account_id))
                if data['suspended']:
                    db.execute('DELETE FROM tickets WHERE account=?', (account_id,))
            if 'quota_bytes' in data:
                quota = data['quota_bytes']
                if type(quota) is not int or not 1 <= quota <= 100_000_000_000_000:
                    raise Fault('Invalid data limit')
                db.execute('UPDATE accounts SET quota=? WHERE id=?', (quota, account_id))
            if 'duration_seconds' in data:
                duration = data['duration_seconds']
                if type(duration) is not int or not 60 <= duration <= 3660 * 86400:
                    raise Fault('Invalid total plan duration')
                expiry = None if row['activated'] is None else row['activated'] + duration
                db.execute('UPDATE accounts SET duration=?,expires=? WHERE id=?', (duration, expiry, account_id))
                row = db.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone()
            if 'extend_seconds' in data:
                extension = data['extend_seconds']
                if type(extension) is not int or not 60 <= extension <= 366 * 86400:
                    raise Fault('Invalid extension duration')
                if row['activated'] is None:
                    db.execute('UPDATE accounts SET duration=duration+? WHERE id=?', (extension, account_id))
                else:
                    expiry = max(self.now(), row['expires']) + extension
                    db.execute('UPDATE accounts SET expires=?,duration=? WHERE id=?', (expiry, expiry-row['activated'], account_id))
            if data.get('reset_device') is True:
                # Preserve activation and expiry. Rebinding never grants a new period.
                db.execute('UPDATE accounts SET key=NULL WHERE id=?', (account_id,))
                for table in ['tokens', 'tickets', 'sessions']:
                    db.execute(f'DELETE FROM {table} WHERE account=?', (account_id,))
                if row['kind'] == 'trial':
                    for table in ['trial_tokens', 'trial_xray_sessions', 'trial_devices']:
                        db.execute(f'DELETE FROM {table} WHERE account=?', (account_id,))
            self.audit(db, 'account_updated', account_id, ','.join(sorted(data)))
        return self.account(account_id)

    def delete_account(self, account_id):
        with self.db() as db:
            if db.execute('UPDATE accounts SET deleted=1,suspended=1,label=? WHERE id=? AND deleted=0', ('Deleted account', account_id)).rowcount != 1:
                raise Fault('Account not found', 404)
            for table in ['tokens', 'tickets', 'sessions', 'trial_tokens', 'trial_xray_sessions', 'trial_devices']:
                db.execute(f'DELETE FROM {table} WHERE account=?', (account_id,))
            self.audit(db, 'account_deleted', account_id)

    def usage(self, account_id, hours=24):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT at,up,down FROM usage WHERE account=? AND at>=? ORDER BY at', (account_id, self.now() - hours * 3600))]

    def audit_list(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200')]

    def maintenance(self, startup=False):
        with self.db() as db:
            if startup:
                db.execute('DELETE FROM sessions')
                db.execute('DELETE FROM tickets')
            for table in ['tokens', 'trial_tokens', 'tickets', 'challenges', 'admin_sessions']:
                db.execute(f'DELETE FROM {table} WHERE expires<=?', (self.now(),))
            db.execute('DELETE FROM usage WHERE at<?', (self.now() - 31 * 86400,))

