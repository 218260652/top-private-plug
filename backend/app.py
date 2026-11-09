"""Same-origin admin UI and JSON API. Run behind HTTPS; see deploy/README.md."""
import asyncio
import fcntl
import json
import logging
import os
import sqlite3
import time
from collections import OrderedDict, deque
from pathlib import Path

from aiohttp import web

from .store import Fault, Store, digest
from . import xray
from .profile_mail import ProfileMailer


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


def create_app(store, public_origin='http://127.0.0.1:8080', secure_cookies=True, gateway_enabled=False, profile_notifier=None, customers_enabled=False):
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
                    await asyncio.to_thread(store.admin_auth, request.cookies.get('tpp_admin', ''))
            if request.path.startswith('/v1/'):
                # Many trial devices can share a NAT address. Bound each bearer
                # separately while preserving an aggregate rate limit per IP.
                authorization = request.headers.get('Authorization', '')
                if authorization.startswith('Bearer '):
                    limiter.check(('api_authenticated', peer(request)), 1800)
                    limiter.check(('api_device', digest(authorization)), 120)
                    await asyncio.to_thread(store.check_network, authorization[7:], request.headers.get('X-TPP-Network'))
                else:
                    limiter.check(('api_public', peer(request)), 360)
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
        return web.json_response({'status': 'ok', 'gateway_enabled': False, 'network_binding_version': 1, 'protocol': 'VLESS/Trojan/Xray', 'connection_method': 'imported-profile'})

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
        return web.json_response({'accounts': accounts, 'profiles': [p for p in store.profiles() if p['engine'] == 'xray'], 'audit': store.audit_list(),
                                  'connection_method': 'imported-profile', 'gateway_enabled': False, 'server_time': store.now(),
                                  **({'customer_admin': '/admin/customers/'} if customers_enabled else {})})

    async def issue(request):
        data = await body(request)
        if data.get('carrier') not in store.NETWORKS:
            raise Fault('Choose the access code network',422)
        selected = data.get('profile_ids')
        if not isinstance(selected, list) or not selected or any(not isinstance(pid, str) for pid in selected):
            raise Fault('Choose at least one imported connection profile')
        if any(store.get_profile(pid).get('engine') != 'xray' for pid in selected):
            raise Fault('Only imported connection profiles can be assigned')
        return web.json_response(store.issue(data), status=201)

    async def account_update(request):
        return web.json_response(store.update_account(request.match_info['id'], await body(request)))

    async def account_delete(request):
        store.delete_account(request.match_info['id'])
        return web.json_response({'ok': True})

    async def profile_save(request):
        raise Fault('Manual server/SNI profiles have been removed. Import your unlocked connection JSON instead.', 410)

    async def xray_import(request):
        return web.json_response(xray.save(store, await body(request), request.match_info.get('id'), notifier=profile_notifier))

    async def import_with_access(request):
        data = await body(request)
        if not isinstance(data.get('access'), dict):
            raise Fault('Provide the activation code limits')
        return web.json_response(xray.save(store, data, notifier=profile_notifier), status=201)

    async def xray_export(request):
        if await body(request):
            raise Fault('Export does not accept options')
        exported = xray.export_profile(store, request.match_info['id'], notifier=profile_notifier)
        return web.json_response(exported, headers={'Content-Disposition': 'attachment; filename="xray-profile.json"'})

    async def xray_toggle(request):
        return web.json_response(xray.toggle(store, request.match_info['id'], await body(request)))

    async def xray_disconnect(request):
        return web.json_response(xray.disconnect(store, token(request), await body(request)))

    async def xray_heartbeat(request):
        return web.json_response(xray.heartbeat(store, token(request), await body(request)))

    async def challenge(request):
        limiter.check(('challenge', peer(request)), 300)
        data = await body(request)
        if data.get('purpose') not in ('activate', 'connect'):
            raise Fault('Invalid challenge purpose')
        return web.json_response(store.challenge(data.get('public_key', ''), data.get('purpose', '')))

    async def activate(request):
        limiter.check(('activate', peer(request)), 150, 300)
        return web.json_response(store.activate(await body(request), require_network=True))

    async def status(request):
        account = store.client_auth(token(request))
        return web.json_response(store.account(account['id']))

    async def profiles(request):
        account = store.client_auth(token(request))
        engines = request.headers.get('X-TPP-Engines', 'tpp').split(',')
        return web.json_response({'profiles': [p for p in store.profiles() if p['id'] in json.loads(account['profiles']) and p['enabled'] and p['engine'] == 'xray' and 'xray' in engines
                and (not account['carrier'] or p['carrier'] in (account['carrier'],'Any'))]})

    async def connect(request):
        store.client_auth(token(request))
        data = await body(request)
        if not isinstance(data.get('profile_id'), str):
            raise Fault('Choose an imported connection profile')
        profile = store.get_profile(data['profile_id'])
        if profile.get('engine') != 'xray':
            raise Fault('Manual server/SNI connections have been removed. Ask your admin to assign an imported profile.', 410)
        if profile.get('insecure_tls') and 'legacy-tls-test-v1' not in request.headers.get('X-TPP-Features', '').split(','):
            raise Fault('This supplier test profile needs Top private Plug 0.1.5 or newer. Install the compatibility APK, then reconnect.', 426)
        return web.json_response(xray.connect(store, token(request), data))

    async def usage(request):
        account = store.client_auth(token(request))
        hours = int(request.query.get('hours', '24'))
        if hours not in [1, 6, 24]:
            raise Fault('Choose 1, 6 or 24 hours')
        return web.json_response({'points': store.usage(account['id'], hours)})

    async def disconnect(request):
        account = store.client_auth(token(request))
        with store.db() as db:
            if account['kind'] == 'trial':
                # Disconnect only this trial device, not its 99 possible peers.
                db.execute('DELETE FROM trial_xray_sessions WHERE account=? AND device_key=?',
                           (account['id'], account['auth_device_key']))
            else:
                db.execute('DELETE FROM sessions WHERE account=?', (account['id'],))
                db.execute('DELETE FROM tickets WHERE account=?', (account['id'],))
                db.execute('DELETE FROM xray_sessions WHERE account=?', (account['id'],))
        return web.json_response({'ok': True})

    async def index(request):
        filename = 'customers.html' if customers_enabled else 'index.html'
        return web.FileResponse(Path(__file__).parent / 'static' / filename)

    async def legacy_admin(request):
        return web.FileResponse(Path(__file__).parent / 'static' / 'index.html')

    async def root(request):
        raise web.HTTPFound('/admin/')

    app = web.Application(middlewares=[security], client_max_size=16384)
    if profile_notifier is not None:
        app.cleanup_ctx.append(profile_notifier.lifecycle)
    app.router.add_get('/health', health)
    app.router.add_get('/setup-status', setup_status)
    app.router.add_get('/', root)
    app.router.add_get('/admin', index)
    app.router.add_get('/admin/', index)
    if customers_enabled:
        app.router.add_get('/admin/legacy/', legacy_admin)
    app.router.add_static('/assets/', Path(__file__).parent / 'static')
    app.router.add_post('/admin/api/login', login)
    app.router.add_post('/admin/api/logout', logout)
    app.router.add_get('/admin/api/state', admin_state)
    app.router.add_post('/admin/api/accounts', issue)
    app.router.add_patch('/admin/api/accounts/{id}', account_update)
    app.router.add_delete('/admin/api/accounts/{id}', account_delete)
    app.router.add_post('/admin/api/profiles', profile_save)
    app.router.add_put('/admin/api/profiles/{id}', profile_save)
    app.router.add_post('/admin/api/xray-profiles', xray_import)
    app.router.add_post('/admin/api/xray-profiles/import-with-access', import_with_access)
    app.router.add_post('/admin/api/xray-profiles/{id}/export', xray_export)
    app.router.add_patch('/admin/api/xray-profiles/{id}', xray_toggle)
    app.router.add_put('/admin/api/xray-profiles/{id}', xray_import)
    app.router.add_post('/v1/xray/disconnect', xray_disconnect)
    app.router.add_post('/v1/xray/heartbeat', xray_heartbeat)
    app.router.add_post('/v1/challenge', challenge)
    app.router.add_post('/v1/activate', activate)
    app.router.add_get('/v1/status', status)
    app.router.add_get('/v1/profiles', profiles)
    app.router.add_get('/v1/usage', usage)
    app.router.add_post('/v1/connect', connect)
    app.router.add_post('/v1/disconnect', disconnect)
    if customers_enabled:
        from .customer import install
        install(app, store, peer, body, token)
    return app


async def main():
    os.umask(0o077)
    database = os.environ.get('DATABASE_URL') or os.environ.get('TPP_DB', 'data/tpp.sqlite3')
    is_postgres = database.startswith(('postgresql://', 'postgres://'))
    customers_enabled = os.environ.get('TPP_CUSTOMER_STAGING') == '1'
    origin = os.environ.get('TPP_PUBLIC_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL', '')
    if customers_enabled:
        from urllib.parse import urlsplit
        if (origin.rstrip('/') != 'https://top-private-plug-test-api.onrender.com' or not is_postgres
                or urlsplit(database).path != '/top_private_plug_test_db'):
            raise SystemExit('Customer staging requires the dedicated HTTPS origin and PostgreSQL database')
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
    local_dev = os.environ.get('TPP_LOCAL_DEV') == '1'
    bind = os.environ.get('TPP_HTTP_BIND', '0.0.0.0' if os.environ.get('RENDER_EXTERNAL_URL') else '127.0.0.1')
    if local_dev and bind not in ['127.0.0.1', '::1']:
        raise SystemExit('Local HTTP development mode must bind to loopback')
    if not local_dev and not origin.startswith('https://'):
        raise SystemExit('Set TPP_PUBLIC_ORIGIN to your public HTTPS origin')
    if customers_enabled:
        with store.db() as db:
            identity = db.execute('SELECT current_database()').fetchone()[0]
        if identity != 'top_private_plug_test_db':
            raise SystemExit('Customer staging requires the dedicated test database')
        from .customer import migrate, provision_staging_networks
        migrate(store)
        staging_profiles = os.environ.get('TPP_STAGING_CARRIER_PROFILES')
        if staging_profiles:
            provision_staging_networks(store, staging_profiles)
    app = create_app(store, origin or 'http://127.0.0.1:8080',
                     secure_cookies=os.environ.get('TPP_LOCAL_DEV') != '1',
                     profile_notifier=None if customers_enabled else ProfileMailer.from_env(store),
                     customers_enabled=customers_enabled)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, bind, int(os.environ.get('TPP_HTTP_PORT') or os.environ.get('PORT', '8080'))).start()
    print('Top private Plug API ready; imported profiles only', flush=True)
    try:
        while True:
            await asyncio.sleep(60)
            store.maintenance()
    finally:
        await runner.cleanup()
        store.close()


if __name__ == '__main__':
    asyncio.run(main())




