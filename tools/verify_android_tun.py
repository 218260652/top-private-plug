#!/usr/bin/env python3
"""Exercise the pinned Xray parser with socket access denied, as on Android.

Checks complete normalized configs, including direct and HTTP-proxied Trojan
outbounds, then reproduces both the unnamed TUN and removed proxy field failures. No supplier credentials or live server needed.
This parser regression does not replace physical Android traffic testing.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.xray import normalize

HARNESS = r'''package main
import (
    "fmt"
    "os"
    "github.com/xtls/xray-core/infra/conf/serial"
)
func main() {
    if _, err := serial.LoadJSONConfig(os.Stdin); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
    fmt.Println("Full Xray config parser passed without interface discovery")
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    raw = {'outbounds': [{'protocol': 'trojan', 'settings': {'servers': [
        {'address': 'vpn.example.com', 'port': 443, 'password': 'not-a-real-credential'}]},
        'streamSettings': {'network': 'tcp', 'security': 'tls', 'tlsSettings': {'serverName': 'vpn.example.com'}}}]}
    direct = normalize(raw)[0]
    raw['outbounds'][0]['proxySettings'] = {'tag': 'supplier-http', 'transportLayer': True}
    raw['outbounds'].append({'protocol': 'http', 'tag': 'supplier-http', 'settings': {
        'servers': [{'address': '192.0.2.1', 'port': 8080}], 'headers': {'Host': 'vpn.example.com:443'}}})
    proxied = normalize(raw)[0]
    current_raw = json.loads(json.dumps(raw))
    current_raw['outbounds'][0].pop('proxySettings')
    current_raw['outbounds'][0]['streamSettings']['sockopt'] = {'dialerProxy': 'supplier-http'}
    current = normalize(current_raw)[0]
    current_raw['outbounds'][0]['streamSettings']['tlsSettings']['allowInsecure'] = True
    insecure = normalize(current_raw, allow_insecure=True)[0]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'main.go').write_text(HARNESS)
        binary = root / 'tun-parser'
        subprocess.run(['go', 'build', '-o', str(binary), str(root / 'main.go')], cwd=args.source.resolve(), check=True)
        command = ['strace', '-qq', '-e', 'trace=socket', '-e', 'inject=socket:error=EACCES', str(binary)]
        for label, config in [('direct', direct), ('legacy HTTP import', proxied), ('current HTTP import', current), ('explicit test TLS', insecure)]:
            fixed = subprocess.run(command, input=json.dumps(config), text=True, capture_output=True)
            if fixed.returncode:
                raise SystemExit('Full config failed (' + label + '): ' + fixed.stderr)
        unnamed = json.loads(json.dumps(proxied))
        unnamed['inbounds'][0]['settings']['name'] = ''
        broken = subprocess.run(command, input=json.dumps(unnamed), text=True, capture_output=True)
        if broken.returncode == 0 or 'fail to get system interface information' not in broken.stderr:
            raise SystemExit('Regression control did not reproduce blocked interface discovery: ' + broken.stderr)
        legacy = json.loads(json.dumps(proxied))
        legacy['outbounds'][0]['streamSettings'].pop('sockopt')
        legacy['outbounds'][0]['proxySettings'] = {'tag': 'http-upstream', 'transportLayer': True}
        broken = subprocess.run(command, input=json.dumps(legacy), text=True, capture_output=True)
        if broken.returncode == 0 or 'proxySettings' not in broken.stderr or 'removed' not in broken.stderr:
            raise SystemExit('Regression control did not reproduce removed proxy field failure: ' + broken.stderr)
        print('PASS: full direct/proxied configs parse with sockets denied; both old TUN and proxy-field failures reproduced.')


if __name__ == '__main__':
    main()
