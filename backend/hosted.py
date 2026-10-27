"""Hosted admin/API entrypoint. Database credentials remain in environment only."""
import os
import subprocess
import sys
from pathlib import Path

from aiohttp import web

from .store import Store


def create_setup_app():
    """Credential-free setup guidance. Never accept account or secret writes."""
    @web.middleware
    async def headers(request, handler):
        response = await handler(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        return response

    async def page(request):
        return web.FileResponse(Path(__file__).parent / 'static' / 'setup.html')

    async def status(request):
        return web.json_response({'status': 'setup_required', 'admin_ready': False, 'gateway_enabled': False})

    async def unavailable(request):
        return web.json_response({'error': 'Owner must finish private hosting configuration before accounts can be managed'}, status=503)

    app = web.Application(middlewares=[headers], client_max_size=16384)
    app.router.add_get('/', page)
    app.router.add_get('/admin', page)
    app.router.add_get('/admin/', page)
    app.router.add_get('/health', status)
    app.router.add_static('/assets/', Path(__file__).parent / 'static')
    app.router.add_route('*', '/{path:.*}', unavailable)
    return app


def main():
    dsn = os.environ.get('DATABASE_URL', '')
    direct = os.environ.get('TPP_MIGRATION_URL', '')
    if not dsn.startswith(('postgres://', 'postgresql://')) or not direct.startswith(('postgres://', 'postgresql://')):
        print('Waiting for owner to configure database credentials privately in hosting settings', flush=True)
        web.run_app(create_setup_app(), host='0.0.0.0', port=int(os.environ.get('PORT', '8080')), access_log=None)
        return
    # Test mutations in a unique isolated schema before applying new schema to public.
    subprocess.run([sys.executable, 'tools/verify_postgres.py', '--from-env'], check=True)
    migration = Store(direct)
    migration.close()
    os.environ['TPP_SKIP_SCHEMA_INIT'] = '1'
    os.execv(sys.executable, [sys.executable, '-m', 'backend.app'])


if __name__ == '__main__':
    main()
