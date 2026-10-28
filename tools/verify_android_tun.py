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
    "crypto/ecdsa"
    "crypto/elliptic"
    "crypto/rand"
    "crypto/x509"
    "math/big"
    "time"
    "github.com/xtls/xray-core/infra/conf"
    coretls "github.com/xtls/xray-core/transport/internet/tls"
    "os"
    "github.com/xtls/xray-core/infra/conf/serial"
)
func main() {
    if len(os.Args) > 1 && os.Args[1] == "--tls-policy" {
        key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader); if err != nil { panic(err) }
        cert := &x509.Certificate{SerialNumber: big.NewInt(1), DNSNames: []string{"localhost"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour)}
        der, err := x509.CreateCertificate(rand.Reader, cert, cert, &key.PublicKey, key); if err != nil { panic(err) }
        for _, insecure := range []bool{false, true} {
            cfg := &conf.TLSConfig{AllowInsecure: insecure, ServerName: "vpn.example.com"}
            built, err := cfg.Build(); if err != nil { panic(err) }
            policy := built.(*coretls.Config).GetTLSConfig()
            if policy.InsecureSkipVerify != insecure { panic("TLS opt-in changed default verification policy") }
            if insecure && policy.VerifyPeerCertificate([][]byte{der}, nil) != nil { panic("Explicit legacy test TLS did not accept the self-signed certificate") }
        }
        verified := &conf.TLSConfig{VerifyPeerCertByName: "vpn.example.com"}
        built, err := verified.Build(); if err != nil { panic(err) }
        if built.(*coretls.Config).GetTLSConfig().VerifyPeerCertificate([][]byte{der}, nil) == nil { panic("Ordinary certificate-name verification was bypassed") }
        fmt.Println("TLS policy verified: ordinary profiles verify certificates; only explicit legacy test mode skips checks")
        return
    }
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
    vless_raw = json.loads(json.dumps(raw))
    vless_raw['outbounds'][0]['protocol'] = 'vless'
    vless_raw['outbounds'][0]['settings'] = {'vnext': [{'address': 'vpn.example.com', 'port': 8446,
        'users': [{'id': '00000000-0000-4000-8000-000000000001', 'encryption': 'none'}]}]}
    vless_raw['outbounds'][0]['streamSettings']['tlsSettings'].update({'fingerprint': 'chrome', 'allowInsecure': True})
    vless_raw['dns'] = {'servers': ['https://1.1.1.1/dns-query', 'https://dns.google/dns-query']}
    vless = normalize(vless_raw, allow_insecure=True)[0]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'main.go').write_text(HARNESS)
        binary = root / 'tun-parser'
        subprocess.run(['go', 'build', '-o', str(binary), str(root / 'main.go')], cwd=args.source.resolve(), check=True, timeout=600)
        subprocess.run([str(binary), '--tls-policy'], check=True, timeout=30)
        command = ['strace', '-f', '-qq', '-e', 'trace=socket', '-e', 'inject=socket:error=EACCES', str(binary)]
        for label, config in [('direct', direct), ('legacy HTTP import', proxied), ('current HTTP import', current), ('explicit test TLS', insecure), ('VLESS HTTP chain and DoH', vless)]:
            fixed = subprocess.run(command, input=json.dumps(config), text=True, capture_output=True, timeout=30)
            if fixed.returncode:
                raise SystemExit('Full config failed (' + label + '): ' + fixed.stderr)
        unnamed = json.loads(json.dumps(proxied))
        unnamed['inbounds'][0]['settings']['name'] = ''
        broken = subprocess.run(command, input=json.dumps(unnamed), text=True, capture_output=True, timeout=30)
        if broken.returncode == 0 or 'fail to get system interface information' not in broken.stderr:
            raise SystemExit('Regression control did not reproduce blocked interface discovery: ' + broken.stderr)
        legacy = json.loads(json.dumps(proxied))
        legacy['outbounds'][0]['streamSettings'].pop('sockopt')
        legacy['outbounds'][0]['proxySettings'] = {'tag': 'http-upstream', 'transportLayer': True}
        broken = subprocess.run(command, input=json.dumps(legacy), text=True, capture_output=True, timeout=30)
        if broken.returncode == 0 or 'proxySettings' not in broken.stderr or 'removed' not in broken.stderr:
            raise SystemExit('Regression control did not reproduce removed proxy field failure: ' + broken.stderr)
        print('PASS: full direct/proxied configs parse with sockets denied; both old TUN and proxy-field failures reproduced.')


if __name__ == '__main__':
    main()

