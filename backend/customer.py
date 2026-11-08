"""Staging customer accounts and VPN authorization, isolated from legacy access codes."""
import asyncio
import json
import os
import re
import secrets
import sqlite3
from pathlib import Path

from aiohttp import web
from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from . import xray
from .store import Fault, digest

CELL_C = 'Cell C'
NETWORKS = ('MTN', 'Telkom', CELL_C)
ACCESS_SECONDS = 300
SESSION_SECONDS = 14 * 86400
LEASE_SECONDS = 30


def hash_password(password):
    return Argon2id(salt=secrets.token_bytes(16), length=32, iterations=2,
                    lanes=1, memory_cost=19456).derive_phc_encoded(password.encode())


def username(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}', value.strip()):
        raise Fault('Use 3 to 40 letters, numbers, dots, hyphens or underscores')
    return value.strip().lower()


def password(value, minimum=12):
    if not isinstance(value, str) or not minimum <= len(value) <= 128:
        raise Fault(f'Password must contain {minimum} to 128 characters')
    return value


def identifier():
    return secrets.token_urlsafe(24)


def bounded(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise Fault(f'Invalid {name}')
    return value


def event(db, now, actor, subject, action):
    db.execute('INSERT INTO customer_events VALUES(?,?,?,?,?)', (identifier(), now, actor, subject, action))


def state(row, now):
    if row['state'] != 'active':
        return row['state']
    if row['starts'] > now:
        return 'pending'
    return 'expired' if row['expires'] <= now else 'active'


def eligible(row, now):
    status = state(row, now)
    if status != 'active':
        raise Fault(f'Account is {status}', 403)


def view(row, now):
    result = dict(row)
    result.pop('password', None)
    result['status'] = state(row, now)
    return result


def customer_view(row, now):
    return {**{key: row[key] for key in ('id','username','starts','expires','device_limit','must_change')},
            'status': state(row, now)}


def is_vless(config):
    return any(item.get('protocol') == 'vless' for item in config.get('outbounds', []))


def migrate(store):
    sql = (Path(__file__).parent / 'migrations' / '001_customer.sql').read_text()
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        for statement in sql.split(';'):
            if statement.strip():
                db.execute(statement)


class Customers:
    def __init__(self, store):
        self.store = store
        self.dummy = hash_password(identifier())

    def attempt(self, bucket, limit, seconds):
        now = self.store.now()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM customer_attempts WHERE bucket=?', (bucket,)).fetchone()
            if not row or row['started'] <= now - seconds:
                db.execute('DELETE FROM customer_attempts WHERE started<=?', (now - 900,))
                db.execute('INSERT INTO customer_attempts VALUES(?,?,1) ON CONFLICT(bucket) DO UPDATE SET started=excluded.started,count=1', (bucket, now))
            elif row['count'] >= limit:
                raise Fault('Too many attempts. Try again later.', 429)
            else:
                db.execute('UPDATE customer_attempts SET count=count+1 WHERE bucket=?', (bucket,))

    def session(self, db, device, now):
        sid, access, refresh = identifier(), identifier(), identifier()
        db.execute('UPDATE customer_sessions SET revoked=1 WHERE device=?', (device,))
        db.execute('DELETE FROM customer_leases WHERE device=?', (device,))
        db.execute('INSERT INTO customer_sessions VALUES(?,?,?,?,?,0)',
                   (sid, device, digest(access), now + ACCESS_SECONDS, now + SESSION_SECONDS))
        db.execute('INSERT INTO customer_refresh VALUES(?,?,0)', (digest(refresh), sid))
        return {'access_token': access, 'refresh_token': refresh, 'expires_in': ACCESS_SECONDS}

    def login(self, data, source):
        try:
            name = username(data.get('username'))
            plain = password(data.get('password'), 1)
        except Fault:
            raise Fault('Invalid username or password', 401) from None
        self.attempt('login-source:' + digest(source), 30, 300)
        self.attempt('login-user:' + digest(name), 8, 300)
        key = data.get('public_key')
        now = self.store.now()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.store.proof(db, data, key, 'customer-login')
            row = db.execute('SELECT * FROM customer_users WHERE username=?', (name,)).fetchone()
        try:
            Argon2id.verify_phc_encoded(plain.encode(), row['password'] if row else self.dummy)
        except InvalidKey:
            with self.store.db() as db:
                event(db, now, 'customer', row['id'] if row else '', 'login_failed')
            raise Fault('Invalid username or password', 401) from None
        if row is None:
            raise Fault('Invalid username or password', 401)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM customer_users WHERE id=?', (row['id'],)).fetchone()
            if current['password'] != row['password']:
                raise Fault('Sign-in details changed. Try again.', 401)
            eligible(current, now)
            device = db.execute('SELECT * FROM customer_devices WHERE customer=? AND public_key=?', (row['id'], key)).fetchone()
            if device and device['revoked']:
                raise Fault('This device is revoked', 403)
            if not device:
                count = db.execute('SELECT COUNT(*) FROM customer_devices WHERE customer=? AND revoked=0', (row['id'],)).fetchone()[0]
                if count >= current['device_limit']:
                    raise Fault('Device limit reached', 409)
                device_id = identifier()
                db.execute('INSERT INTO customer_devices VALUES(?,?,?,?,?,0)', (device_id, row['id'], key, now, now))
            else:
                device_id = device['id']
                db.execute('UPDATE customer_devices SET seen=? WHERE id=?', (now, device_id))
            result = self.session(db, device_id, now)
            db.execute('UPDATE customer_users SET last_login=? WHERE id=?', (now, row['id']))
            event(db, now, 'customer', row['id'], 'login')
            return {**result, 'account': customer_view(current, now)}

    def refresh(self, data):
        raw = password(data.get('refresh_token'), 20)
        now = self.store.now()
        replay = False
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("""SELECT r.used,s.id,s.expires,s.revoked,d.public_key,d.customer,d.revoked AS blocked
                              FROM customer_refresh r JOIN customer_sessions s ON s.id=r.session
                              JOIN customer_devices d ON d.id=s.device WHERE r.hash=?""", (digest(raw),)).fetchone()
            if not row or row['revoked'] or row['blocked'] or row['expires'] <= now:
                raise Fault('Sign in again', 401)
            self.store.proof(db, data, row['public_key'], 'customer-refresh')
            if row['used']:
                replay = True
                db.execute('UPDATE customer_sessions SET revoked=1 WHERE id=?', (row['id'],))
                db.execute('DELETE FROM customer_leases WHERE session=?', (row['id'],))
                event(db, now, 'security', row['customer'], 'refresh_replay')
            else:
                eligible(db.execute('SELECT * FROM customer_users WHERE id=?', (row['customer'],)).fetchone(), now)
                access, refresh = identifier(), identifier()
                db.execute('UPDATE customer_refresh SET used=1 WHERE hash=?', (digest(raw),))
                db.execute('UPDATE customer_sessions SET access=?,access_until=? WHERE id=?',
                           (digest(access), now + ACCESS_SECONDS, row['id']))
                db.execute('INSERT INTO customer_refresh VALUES(?,?,0)', (digest(refresh), row['id']))
        if replay:
            raise Fault('Session revoked. Sign in again.', 401)
        return {'access_token': access, 'refresh_token': refresh, 'expires_in': ACCESS_SECONDS}

    def authenticated(self, db, token, now):
        row = db.execute("""SELECT u.*, d.id AS device, d.public_key, s.id AS session
                         FROM customer_sessions s JOIN customer_devices d ON d.id=s.device
                         JOIN customer_users u ON u.id=d.customer
                         WHERE s.access=? AND s.access_until>? AND s.expires>? AND s.revoked=0 AND d.revoked=0""",
                         (digest(token), now, now)).fetchone()
        if not row:
            raise Fault('Sign in again', 401)
        return row

    def network_rows(self, db):
        profiles = []
        for row in db.execute("""SELECT n.carrier,n.profile,CASE WHEN n.tested=p.version THEN 1 ELSE 0 END AS tested,
            p.name,p.version,p.enabled,x.insecure,x.config
            FROM customer_networks n JOIN profiles p ON p.id=n.profile
            JOIN xray_profiles x ON x.profile=p.id WHERE n.carrier IN (?,?,?) ORDER BY n.carrier""", NETWORKS):
            item = dict(row)
            if not is_vless(json.loads(item.pop('config'))) or (item['carrier'] == CELL_C and not os.environ.get('TPP_CELL_C_CODE')):
                item['enabled'] = item['tested'] = 0
            profiles.append(item)
        return profiles

    def customer(self, op, token, data):
        now = self.store.now()
        with self.store.db() as db:
            if op not in ('profile', 'networks', 'devices'):
                db.execute('BEGIN IMMEDIATE')
            row = self.authenticated(db, token, now)
            if op == 'logout':
                db.execute('UPDATE customer_sessions SET revoked=1 WHERE id=?', (row['session'],))
                db.execute('DELETE FROM customer_leases WHERE session=?', (row['session'],))
                event(db, now, 'customer', row['id'], 'logout')
                return {'ok': True}
            eligible(row, now)
            if op == 'profile':
                return customer_view(row, now)
            if op == 'password':
                self.store.proof(db, data, row['public_key'], 'customer-password')
                replacement = hash_password(password(data.get('password')))
                db.execute('UPDATE customer_users SET password=?,must_change=0 WHERE id=?', (replacement,row['id']))
                self.revoke(db, row['id'])
                event(db, now, 'customer', row['id'], 'password_changed')
                return self.session(db, row['device'], now)
            if row['must_change']:
                raise Fault('Change your temporary password first', 403)
            if op == 'networks':
                profiles = {p['carrier']:p for p in self.network_rows(db)}
                return {'networks': [profiles.get(name, {'carrier':name,'enabled':0,'tested':0}) for name in NETWORKS]}
            if op == 'devices':
                return {'devices': self.devices(db, row['id'])}
            if op == 'revoke-device':
                self.store.proof(db, data, row['public_key'], 'customer-device')
                self.revoke_device(db, row['id'], data.get('device',''), now, 'customer')
                return {'ok': True}
            if op == 'connect':
                return self.connect(db, row, data, now)
            lease = data.get('lease', '')
            if not isinstance(lease,str) or len(lease) > 100:
                raise Fault('Invalid lease')
            entry = db.execute('SELECT * FROM customer_leases WHERE hash=? AND device=? AND session=?',
                               (digest(lease),row['device'],row['session'])).fetchone()
            if op == 'disconnect':
                if entry:
                    db.execute('DELETE FROM customer_leases WHERE hash=?', (entry['hash'],))
                    event(db,now,'customer',row['id'],'vpn_disconnected')
                return {'ok': True}
            profile = next((p for p in self.network_rows(db) if entry and p['carrier']==entry['carrier']), None)
            if not entry or entry['expires'] <= now or not profile or not profile['enabled'] or profile['insecure'] or profile['profile'] != entry['profile'] or profile['version'] != entry['version']:
                raise Fault('Connection authorization expired or changed', 403)
            seconds = min(LEASE_SECONDS, row['expires'] - now)
            db.execute('UPDATE customer_leases SET expires=?,seen=? WHERE hash=?',(now+seconds,now,entry['hash']))
            db.execute('UPDATE customer_devices SET seen=? WHERE id=?',(now,row['device']))
            return {'ok':True, 'lease_seconds':seconds, 'enforcement':'app-reported'}

    def connect(self, db, row, data, now):
        self.store.proof(db, data, row['public_key'], 'customer-connect')
        carrier = data.get('carrier')
        p = next((profile for profile in self.network_rows(db) if profile['carrier']==carrier), None)
        if not p or not p['enabled'] or p['insecure']:
            raise Fault('This network profile is unavailable', 403)
        if carrier == CELL_C:
            code = data.get('carrier_code')
            expected = os.environ.get('TPP_CELL_C_CODE', '')
            if (not expected or not isinstance(code, str) or len(code) > 128
                    or not secrets.compare_digest(code.encode('utf-8', 'surrogatepass'), expected.encode())):
                raise Fault('Incorrect Cell C code', 403)
        entry = db.execute('SELECT expires FROM customer_leases WHERE device=?',(row['device'],)).fetchone()
        if entry and entry['expires'] > now:
            raise Fault('This device already has a connection authorization', 409)
        item = db.execute('SELECT config FROM xray_profiles WHERE profile=?',(p['profile'],)).fetchone()
        config = xray.normalize(json.loads(item['config']))[0]
        lease, seconds = identifier(), min(LEASE_SECONDS,row['expires']-now)
        db.execute('DELETE FROM customer_leases WHERE device=?',(row['device'],))
        db.execute('INSERT INTO customer_leases VALUES(?,?,?,?,?,?,?,NULL)',
                   (digest(lease),row['device'],row['session'],carrier,p['profile'],p['version'],now+seconds))
        event(db,now,'customer',row['id'],'vpn_authorized')
        return {'engine':'xray','profile':p,'config':config,'lease':lease,'lease_seconds':seconds}

    @staticmethod
    def devices(db, customer):
        return [dict(row) for row in db.execute(
            'SELECT id,created,seen,revoked FROM customer_devices WHERE customer=? ORDER BY created DESC',(customer,))]

    @staticmethod
    def revoke(db, customer):
        db.execute('DELETE FROM customer_leases WHERE device IN (SELECT id FROM customer_devices WHERE customer=?)',(customer,))
        db.execute('UPDATE customer_sessions SET revoked=1 WHERE device IN (SELECT id FROM customer_devices WHERE customer=?)',(customer,))

    @staticmethod
    def revoke_device(db, customer, device, now, actor):
        if not db.execute('UPDATE customer_devices SET revoked=1 WHERE customer=? AND id=?',(customer,device)).rowcount:
            raise Fault('Device not found',404)
        db.execute('DELETE FROM customer_leases WHERE device=?',(device,))
        db.execute('UPDATE customer_sessions SET revoked=1 WHERE device=?',(device,))
        event(db,now,actor,customer,'device_revoked')

    def admin(self, op, actor, data, customer='', query=''):
        now = self.store.now()
        with self.store.db() as db:
            if op not in ('overview','users','user'):
                db.execute('BEGIN IMMEDIATE')
            if op == 'overview':
                counts = {key:0 for key in ('active','expired','paused','suspended','revoked','pending')}
                for row in db.execute('SELECT state,starts,expires FROM customer_users'):
                    status = state(row,now)
                    if status != 'deleted':
                        counts[status] += 1
                return {'counts':counts,'registered_devices':db.execute('SELECT COUNT(*) FROM customer_devices WHERE revoked=0').fetchone()[0],
                        'recent_client_heartbeats':db.execute('SELECT COUNT(*) FROM customer_leases WHERE expires>? AND seen>?',(now,now-15)).fetchone()[0],
                        'gateway_connection_count':None,'database':'reachable',
                        'events':[dict(r) for r in db.execute('SELECT * FROM customer_events ORDER BY at DESC,id DESC LIMIT 50')],
                        'networks':self.network_rows(db),
                        'profiles':[dict(r) for r in db.execute("""SELECT p.id,p.name,p.carrier,p.enabled,x.insecure
                            FROM profiles p JOIN xray_profiles x ON x.profile=p.id ORDER BY p.name""")],
                        'plans':[dict(r) for r in db.execute('SELECT * FROM customer_plans ORDER BY days,name')]}
            if op == 'users':
                needle = query.lower()[:80]
                return {'users':[view(r,now) for r in db.execute("""SELECT * FROM customer_users
                    WHERE state<>'deleted' AND (strpos(username,?)>0 OR strpos(lower(name),?)>0) ORDER BY created DESC,id DESC LIMIT 100"""
                    if self.store.postgres else """SELECT * FROM customer_users
                    WHERE state<>'deleted' AND (instr(username,?)>0 OR instr(lower(name),?)>0) ORDER BY created DESC,id DESC LIMIT 100""",(needle,needle))]}
            if op == 'plan':
                name = self.label(data.get('name'),80)
                days = bounded(data.get('days'),1,366,'plan days')
                cents = bounded(data.get('price_cents'),0,100_000_000,'plan price in cents')
                plan = data.get('id') or identifier()
                if not isinstance(plan,str) or len(plan)>100:
                    raise Fault('Invalid plan ID')
                db.execute("""INSERT INTO customer_plans VALUES(?,?,?,?) ON CONFLICT(id)
                    DO UPDATE SET name=excluded.name,days=excluded.days,price_cents=excluded.price_cents""",(plan,name,days,cents))
                event(db,now,actor,plan,'plan_saved')
                return {'id':plan}
            if op == 'network':
                carrier, profile = data.get('carrier'),data.get('profile')
                tested = data.get('tested',False)
                if carrier not in NETWORKS or type(tested) is not bool or not isinstance(profile,str):
                    raise Fault('Invalid network assignment')
                if profile:
                    row = db.execute("""SELECT p.version,x.config FROM profiles p JOIN xray_profiles x ON x.profile=p.id
                        WHERE p.id=? AND p.carrier IN (?, 'Any') AND x.insecure=0""",(profile,carrier)).fetchone()
                    if not row or not is_vless(json.loads(row['config'])):
                        raise Fault('Choose a certificate-verified VLESS import for this network')
                    db.execute("""INSERT INTO customer_networks VALUES(?,?,?) ON CONFLICT(carrier)
                         DO UPDATE SET profile=excluded.profile,tested=excluded.tested""",(carrier,profile,row['version'] if tested else 0))
                else:
                    db.execute('DELETE FROM customer_networks WHERE carrier=?',(carrier,))
                db.execute('DELETE FROM customer_leases WHERE carrier=?',(carrier,))
                event(db,now,actor,carrier,'network_updated')
                return {'ok':True}
            if op == 'create':
                name = username(data.get('username'))
                if db.execute('SELECT 1 FROM customer_users WHERE username=?',(name,)).fetchone():
                    raise Fault('Username already exists',409)
                limit = bounded(data.get('device_limit'),1,50,'device limit')
                plan = data.get('plan')
                if plan:
                    plan_row = db.execute('SELECT days FROM customer_plans WHERE id=?',(plan,)).fetchone()
                    if not plan_row:
                        raise Fault('Plan not found',404)
                    days = plan_row['days']
                else:
                    days = bounded(data.get('days'),1,366,'subscription days')
                customer = identifier()
                plain = password(data.get('password') or identifier())
                initial_state = data.get('state','active')
                if initial_state not in ('active','suspended'):
                    raise Fault('Invalid account status')
                db.execute('INSERT INTO customer_users VALUES(?,?,?,?,?,?,?,?,?,?,0,NULL)',
                           (customer,name,hash_password(plain),self.label(data.get('name',''),100),
                            self.label(data.get('notes',''),500),initial_state,now,now,now+days*86400,limit))
                event(db,now,actor,customer,'customer_created')
                return {'id':customer,'initial_password':plain}
            row = db.execute('SELECT * FROM customer_users WHERE id=?',(customer,)).fetchone()
            if not row:
                raise Fault('Customer not found',404)
            if row['state'] == 'deleted':
                raise Fault('Customer not found',404)
            if op == 'lifecycle':
                action = data.get('action')
                if row['state'] == 'revoked' and action != 'delete':
                    raise Fault('Account is revoked',409)
                changes = {'pause':'paused','suspend':'suspended','resume':'active','delete':'deleted'}
                if action == 'renew':
                    days = bounded(data.get('days'),1,366,'renewal days')
                    expiry = max(now,row['expires']) + days*86400
                    db.execute('UPDATE customer_users SET expires=? WHERE id=?',(expiry,customer))
                elif isinstance(action,str) and action in changes:
                    if action == 'resume' and row['state'] not in ('paused','suspended'):
                        raise Fault('Only paused or suspended accounts can be resumed',409)
                    db.execute('UPDATE customer_users SET state=? WHERE id=?',(changes[action],customer))
                    if action != 'resume':
                        self.revoke(db,customer)
                    if action == 'delete':
                        db.execute('UPDATE customer_devices SET revoked=1 WHERE customer=?',(customer,))
                else:
                    raise Fault('Invalid account action')
                event(db,now,actor,customer,'customer_' + action)
                return {'ok':True}
            if op == 'user':
                return {'user':view(row,now),'devices':self.devices(db,customer),
                        'events':[dict(r) for r in db.execute('SELECT * FROM customer_events WHERE subject=? ORDER BY at DESC,id DESC LIMIT 50',(customer,))]}
            if op == 'revoke-device':
                self.revoke_device(db,customer,data.get('device',''),now,actor)
                return {'ok':True}
            if op == 'reset':
                if row['state']=='revoked':
                    raise Fault('Account is revoked',409)
                plain = identifier()
                db.execute('UPDATE customer_users SET password=?,must_change=1 WHERE id=?',(hash_password(plain),customer))
                self.revoke(db,customer)
                event(db,now,actor,customer,'password_reset')
                return {'temporary_password':plain}
            if row['state']=='revoked':
                raise Fault('Account is revoked',409)
            current_state = data.get('state',row['state'])
            if current_state not in ('active','paused','suspended','revoked'):
                raise Fault('Invalid account status')
            expires = bounded(data.get('expires',row['expires']),row['starts'],now+3660*86400,'subscription expiry')
            limit = bounded(data.get('device_limit',row['device_limit']),1,50,'device limit')
            count = db.execute('SELECT COUNT(*) FROM customer_devices WHERE customer=? AND revoked=0',(customer,)).fetchone()[0]
            if count > limit:
                raise Fault('Revoke excess devices before lowering this limit',409)
            db.execute('UPDATE customer_users SET name=?,notes=?,state=?,expires=?,device_limit=? WHERE id=?',
                       (self.label(data.get('name',row['name']),100),self.label(data.get('notes',row['notes']),500),
                        current_state,expires,limit,customer))
            if current_state != 'active' or expires <= now:
                self.revoke(db,customer)
            event(db,now,actor,customer,'customer_updated:' + current_state)
            return {'ok':True}

    @staticmethod
    def label(value, maximum):
        if not isinstance(value,str) or len(value)>maximum:
            raise Fault('Invalid text field')
        return value.strip()


def install(app, store, peer, body, token):
    service = Customers(store)
    workers = asyncio.Semaphore(4)
    public_ops = {'login','refresh','challenge'}
    read_ops = {'profile','subscription','networks','devices','status'}
    write_ops = {'password','logout','revoke-device','connect','heartbeat','disconnect'}
    purposes = {'customer-' + op for op in ('login','refresh','password','device','connect')}

    def customer_operation(op, source, bearer, data):
        if op == 'challenge':
            key = data.get('public_key')
            if data.get('purpose') not in purposes or not isinstance(key,str) or len(key)>256:
                raise Fault('Invalid device challenge')
            service.attempt('challenge:' + digest(source), 120, 60)
            return store.challenge(key,data['purpose'])
        if op == 'login':
            return service.login(data,source)
        if op == 'refresh':
            service.attempt('refresh:' + digest(source), 90, 60)
            return service.refresh(data)
        if op == 'connect' and data.get('carrier') == CELL_C:
            service.attempt('cell-c:' + digest(source), 20, 60)
        if op in ('subscription','status'):
            op = 'profile'
        return service.customer(op,bearer,data)

    async def customer_api(request):
        op = request.match_info['op']
        allowed = read_ops if request.method == 'GET' else public_ops | write_ops
        if op not in allowed:
            raise web.HTTPNotFound()
        bearer = '' if op in public_ops else token(request)
        if op not in public_ops and not re.fullmatch(r'[A-Za-z0-9_-]{32}',bearer):
            raise Fault('Sign in again',401)
        data = await body(request) if request.method=='POST' else {}
        if request.method=='POST' and op in ('login','password','refresh','connect','revoke-device'):
            if any(not isinstance(data.get(k),str) or len(data[k])>256 for k in ('public_key','challenge_id','signature')):
                raise Fault('Device proof required',401)
        if op not in public_ops:
            service_limit.check(('customer-api',digest(bearer)),120)
        async with workers:
            return web.json_response(await asyncio.to_thread(customer_operation,op,peer(request),bearer,data))

    async def admin_api(request):
        op = request.match_info['op']
        allowed = {'overview','users','user'} if request.method=='GET' else {'create','update','reset','revoke-device','network','plan','lifecycle'}
        if op not in allowed:
            raise web.HTTPNotFound()
        data = await body(request) if request.method=='POST' else {}
        customer = request.query.get('id','') if request.method=='GET' else data.get('id','')
        if not isinstance(customer,str) or len(customer)>100:
            raise Fault('Invalid account ID')
        async with workers:
            return web.json_response(await asyncio.to_thread(service.admin,op,'legacy-admin:1',data,customer,request.query.get('q','')))

    async def admin_page(request):
        return web.FileResponse(Path(__file__).parent / 'static' / 'customers.html')

    from .app import Limiter
    service_limit = Limiter()
    app.router.add_get('/v2/customer/{op}',customer_api)
    app.router.add_post('/v2/customer/{op}',customer_api)
    app.router.add_get('/admin/customers/',admin_page)
    app.router.add_get('/admin/api/customers/{op}',admin_api)
    app.router.add_post('/admin/api/customers/{op}',admin_api)
