"""Same-origin admin UI and JSON API. Run behind HTTPS; see deploy/README.md."""
import asyncio
import fcntl
import json
import logging
import os
import sqlite3
import ssl
import time
from collections import OrderedDict, deque
from pathlib import Path

from aiohttp import web

from .gateway import Gateway
from .store import Fault, Store


class Limiter:
    def __init__(self):
        self.buckets = OrderedDict()

    def check(self, key, count=30, window=60):
        now = time.monotonic()
        bucket = self.buckets.setdefault(key, deque())
        self.buckets.move_to_end(key)
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= count:
            raise Fault('Too many attempts; try again later', 429)
        bucket.append(now)
        while len(self.buckets) > 10000:
            self.buckets.popitem(last=False)


def create_app(store, public_origin='http://127.0.0.1:8080', secure_cookies=True, gateway_enabled=False):
    limiter = Limiter()
    public_origin = public_origin.rstrip('/')

    @web.middleware
    async def security(request, handler):
        try:
            if request.path.startswith('/admin/api/'):
                if request.method not in ['GET', 'HEAD']:
                    if request.headers.get('Origin') != public_origin or request.headers.get('X-TPP-Request') != '1':
                        raise Fault('Request origin rejected', 403)
                if request.path != '/admin/api/login':
                    store.admin_auth(request.cookies.get('tpp_admin', ''))
            if request.path.startswith('/v1/'):
                # Only trust forwarded client IP from a loopback reverse proxy.
                limiter.check(('api', peer(request)), 120)
            response = await handler(request)
        except Fault as error:
            response = web.json_response({'error': error.message}, status=error.status)
        except (json.JSONDecodeError, UnicodeError, KeyError, TypeError, ValueError):
            response = web.json_response({'error': 'Invalid request'}, status=400)
        except sqlite3.Error:
            logging.exception('Database operation failed')
            response = web.json_response({'error': 'Service temporarily unavailable'}, status=503)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if secure_cookies:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    def peer(request):
        remote = request.remote or 'unknown'
        forwarded = request.headers.get('X-Forwarded-For', '')
        if remote in ['127.0.0.1', '::1'] and forwarded:
            return forwarded.split(',')[-1].strip()
        return remote

    async def body(request):
        if request.content_type != 'application/json':
            raise Fault('Use application/json')
        data = await request.json()
        if not isinstance(data, dict):
            raise Fault('JSON object required')
        return data

    def token(request):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            raise Fault('Activate your access code', 401)
        return header[7:]

    async def health(request):
        return web.json_response({'status': 'ok', 'gateway_enabled': gateway_enabled, 'protocol': 'TPP/1'})

    async def setup_status(request):
        return web.json_response({'setup_required': not store.has_admin()})

    async def login(request):
        limiter.check(('login', peer(request)), 5, 300)
        data = await body(request)
        cookie = store.login(data.get('username', ''), data.get('password', ''), data.get('otp', ''))
        response = web.json_response({'ok': True})
        response.set_cookie('tpp_admin', cookie, httponly=True, secure=secure_cookies, samesite='Strict', path='/admin', max_age=28800)
        return response

    async def logout(request):
        store.logout(request.cookies.get('tpp_admin', ''))
        response = web.json_response({'ok': True})
        response.del_cookie('tpp_admin', path='/admin')
        return response

    async def admin_state(request):
        accounts = store.accounts()
        return web.json_response({'accounts': accounts, 'profiles': store.profiles(), 'audit': store.audit_list(),
                                  'gateway_enabled': gateway_enabled, 'server_time': store.now()})

    async def issue(request):
        return web.json_response(store.issue(await body(request)), status=201)

    async def account_update(request):
        return web.json_response(store.update_account(request.match_info['id'], await body(request)))

    async def account_delete(request):
        store.delete_account(request.match_info['id'])
        return web.json_response({'ok': True})

    async def profile_save(request):
        return web.json_response(store.save_profile(await body(request), request.match_info.get('id')))

    async def challenge(request):
        limiter.check(('challenge', peer(request)), 30)
        data = await body(request)
        return web.json_response(store.challenge(data.get('public_key', ''), data.get('purpose', '')))

    async def activate(request):
        limiter.check(('activate', peer(request)), 10, 300)
        return web.json_response(store.activate(await body(request)))

    async def status(request):
        account = store.client_auth(token(request))
        return web.json_response(store.account(account['id']))

    async def profiles(request):
        account = store.client_auth(token(request))
        return web.json_response({'profiles': [p for p in store.profiles() if p['id'] in json.loads(account['profiles']) and p['enabled']]})

    async def connect(request):
        if not gateway_enabled:
            raise Fault('VPN gateway is not configured yet', 503)
        return web.json_response(store.connect(token(request), await body(request)))

    async def usage(request):
        account = store.client_auth(token(request))
        hours = int(request.query.get('hours', '24'))
        if hours not in [1, 6, 24]:
            raise Fault('Choose 1, 6 or 24 hours')
        return web.json_response({'points': store.usage(account['id'], hours)})

    async def disconnect(request):
        account = store.client_auth(token(request))
        with store.db() as db:
            db.execute('DELETE FROM sessions WHERE account=?', (account['id'],))
            db.execute('DELETE FROM tickets WHERE account=?', (account['id'],))
        return web.json_response({'ok': True})

    async def index(request):
        return web.FileResponse(Path(__file__).parent / 'static' / 'index.html')

    async def root(request):
        raise web.HTTPFound('/admin/')

    app = web.Application(middlewares=[security], client_max_size=16384)
    app.router.add_get('/health', health)
    app.router.add_get('/setup-status', setup_status)
    app.router.add_get('/', root)
    app.router.add_get('/admin', index)
    app.router.add_get('/admin/', index)
    app.router.add_static('/assets/', Path(__file__).parent / 'static')
    app.router.add_post('/admin/api/login', login)
    app.router.add_post('/admin/api/logout', logout)
    app.router.add_get('/admin/api/state', admin_state)
    app.router.add_post('/admin/api/accounts', issue)
    app.router.add_patch('/admin/api/accounts/{id}', account_update)
    app.router.add_delete('/admin/api/accounts/{id}', account_delete)
    app.router.add_post('/admin/api/profiles', profile_save)
    app.router.add_put('/admin/api/profiles/{id}', profile_save)
    app.router.add_post('/v1/challenge', challenge)
    app.router.add_post('/v1/activate', activate)
    app.router.add_get('/v1/status', status)
    app.router.add_get('/v1/profiles', profiles)
    app.router.add_get('/v1/usage', usage)
    app.router.add_post('/v1/connect', connect)
    app.router.add_post('/v1/disconnect', disconnect)
    return app


async def main():
    os.umask(0o077)
    database = os.environ.get('DATABASE_URL') or os.environ.get('TPP_DB', 'data/tpp.sqlite3')
    is_postgres = database.startswith(('postgresql://', 'postgres://'))
    if not is_postgres:
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    process_lock = open('/tmp/top-private-plug.lock' if is_postgres else database + '.lock', 'a')
    try:
        fcntl.flock(process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Another Top private Plug process is already using this database')
    store = Store(database, initialize=os.environ.get('TPP_SKIP_SCHEMA_INIT') != '1')
    # A web-only restart must not revoke a separately hosted gateway's sessions.
    store.maintenance(startup=not is_postgres)
    bootstrap_password = os.environ.get('TPP_BOOTSTRAP_PASSWORD', '')
    if bootstrap_password and not store.has_admin():
        store.bootstrap('admin', bootstrap_password)
    cert, key = os.environ.get('TPP_TLS_CERT', ''), os.environ.get('TPP_TLS_KEY', '')
    enabled = bool(cert and key)
    local_dev = os.environ.get('TPP_LOCAL_DEV') == '1'
    origin = os.environ.get('TPP_PUBLIC_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL', '')
    bind = os.environ.get('TPP_HTTP_BIND', '0.0.0.0' if os.environ.get('RENDER_EXTERNAL_URL') else '127.0.0.1')
    if local_dev and bind not in ['127.0.0.1', '::1']:
        raise SystemExit('Local HTTP development mode must bind to loopback')
    if not local_dev and not origin.startswith('https://'):
        raise SystemExit('Set TPP_PUBLIC_ORIGIN to your public HTTPS origin')
    gateway = Gateway(store)
    if enabled:
        await gateway.start(os.environ.get('TPP_GATEWAY_BIND', '0.0.0.0'), int(os.environ.get('TPP_GATEWAY_PORT', '443')), cert, key)
    app = create_app(store, origin or 'http://127.0.0.1:8080',
                     secure_cookies=os.environ.get('TPP_LOCAL_DEV') != '1',
                     gateway_enabled=enabled or os.environ.get('TPP_REMOTE_GATEWAY') == '1')
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, bind, int(os.environ.get('TPP_HTTP_PORT') or os.environ.get('PORT', '8080'))).start()
    print('Top private Plug API ready; gateway=' + str(enabled), flush=True)
    try:
        while True:
            await asyncio.sleep(60)
            store.maintenance()
            if enabled:
                try:
                    gateway.context.load_cert_chain(cert, key)
                except (OSError, ssl.SSLError):
                    logging.error('TLS certificate reload failed; existing certificate remains active')
    finally:
        await gateway.close()
        await runner.cleanup()
        store.close()


if __name__ == '__main__':
    asyncio.run(main())
