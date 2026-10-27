"""Separate Linux packet gateway using the hosted admin's PostgreSQL database.

Requires a TUN-capable Linux host, NAT/firewall setup and an owned TLS certificate.
Run only one gateway process for this pilot. It is not a Render web workload.
"""
import asyncio
import os

from .gateway import Gateway
from .store import Store


async def main():
    os.umask(0o077)
    dsn = os.environ.get('DATABASE_URL', '')
    cert, key = os.environ.get('TPP_TLS_CERT', ''), os.environ.get('TPP_TLS_KEY', '')
    if not dsn or not cert or not key:
        raise SystemExit('Set DATABASE_URL, TPP_TLS_CERT and TPP_TLS_KEY securely on the gateway')
    store = Store(dsn, initialize=False)
    store.maintenance(startup=True)
    gateway = Gateway(store)
    await gateway.start(os.environ.get('TPP_GATEWAY_BIND', '0.0.0.0'), int(os.environ.get('TPP_GATEWAY_PORT', '8443')), cert, key)
    print('TLS VPN gateway listener started; verify real routing before selling access', flush=True)
    try:
        while True:
            await asyncio.sleep(60)
            gateway.context.load_cert_chain(cert, key)
    finally:
        await gateway.close()
        store.close()


if __name__ == '__main__':
    asyncio.run(main())
