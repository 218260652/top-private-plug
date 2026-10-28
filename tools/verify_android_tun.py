#!/usr/bin/env python3
"""Exercise the pinned Xray parser with socket access denied, as on Android.

Checks the exact normalized inbound, then proves the old unnamed configuration
fails under the same restriction. No supplier credentials or live server needed.
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
    "encoding/json"
    "fmt"
    "os"
    "github.com/xtls/xray-core/infra/conf"
)
func main() {
    var config conf.TunConfig
    if err := json.NewDecoder(os.Stdin).Decode(&config); err != nil { panic(err) }
    if _, err := config.Build(); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
    fmt.Println("TUN parser passed without interface discovery")
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    raw = {'outbounds': [{'protocol': 'trojan', 'settings': {'servers': [
        {'address': 'vpn.example.com', 'port': 443, 'password': 'not-a-real-credential'}]},
        'streamSettings': {'network': 'tcp', 'security': 'tls', 'tlsSettings': {'serverName': 'vpn.example.com'}}}]}
    config = normalize(raw)[0]['inbounds'][0]['settings']
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'main.go').write_text(HARNESS)
        binary = root / 'tun-parser'
        subprocess.run(['go', 'build', '-o', str(binary), str(root / 'main.go')], cwd=args.source.resolve(), check=True)
        command = ['strace', '-qq', '-e', 'trace=socket', '-e', 'inject=socket:error=EACCES', str(binary)]
        fixed = subprocess.run(command, input=json.dumps(config), text=True, capture_output=True)
        if fixed.returncode:
            raise SystemExit('Named Android configuration failed: ' + fixed.stderr)
        old = dict(config, name='')
        broken = subprocess.run(command, input=json.dumps(old), text=True, capture_output=True)
        if broken.returncode == 0 or 'fail to get system interface information' not in broken.stderr:
            raise SystemExit('Regression control did not reproduce blocked interface discovery: ' + broken.stderr)
        print('PASS: emitted Android TUN config parses with socket syscalls denied; unnamed control reproduces permission failure.')


if __name__ == '__main__':
    main()
