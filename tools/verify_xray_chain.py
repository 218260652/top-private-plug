#!/usr/bin/env python3
"""Exercise normalized VLESS/TLS through a real loopback HTTP CONNECT proxy."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.xray import normalize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    raw = {'outbounds': [
        {'protocol': 'vless', 'settings': {'vnext': [{'address': '127.0.0.1', 'port': 443,
            'users': [{'id': '00000000-0000-4000-8000-000000000001', 'encryption': 'none'}]}]},
         'streamSettings': {'network': 'tcp', 'security': 'tls',
             'tlsSettings': {'serverName': 'fixture.invalid', 'fingerprint': 'chrome', 'allowInsecure': True}},
         'proxySettings': {'tag': 'fixture-http', 'transportLayer': True}},
        {'tag': 'fixture-http', 'protocol': 'http', 'settings': {
            'servers': [{'address': '127.0.0.1', 'port': 8080}],
            'headers': {'User-Agent': 'tpp-loopback-fixture', 'X-iorg-bsid': 'fixture-only'}}}]}
    config = normalize(raw, True)[0]
    # The test exercises the outbound path used by measureDelay, without an OS TUN.
    config['inbounds'] = []
    config['log']['loglevel'] = 'debug'
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / 'chain-test'
        subprocess.run(['go', 'build', '-o', str(binary), str(Path(__file__).with_name('xray_chain_harness.go').resolve())],
                       cwd=args.source.resolve(), check=True, timeout=600)
        subprocess.run([str(binary)], input=json.dumps(config), text=True, check=True, timeout=90)


if __name__ == '__main__':
    main()
