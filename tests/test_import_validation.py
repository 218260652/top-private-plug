import json
import subprocess
import unittest
from pathlib import Path
from backend import xray
from backend.store import Fault


def fixture(port='443', identity='00000000000040008000000000000001'):
    return {'outbounds': [{'protocol': 'vless', 'settings': {'vnext': [
        {'address': 'vpn.example.com', 'port': port, 'users': [{'id': identity}]}]},
        'streamSettings': {'network': 'ws', 'security': 'tls',
                           'wsSettings': {'path': '/baron', 'headers': {'Host': 'ws.example.com'}}}}]}


class ImportValidationTests(unittest.TestCase):
    def test_custom_ids_match_xray_mapping(self):
        for identity, expected in [
            ('olise', '75215ecd-3575-5923-ae17-6377c4a6c66c'),
            # Published Xray documentation example: guards namespace/encoding.
            ('我爱🍉老师1314', '5783a3e7-e373-51cd-8642-c83782b807c5'),
        ]:
            raw = fixture(identity=identity)
            normalized = xray.normalize(raw)[0]
            self.assertEqual(normalized['outbounds'][0]['settings']['vnext'][0]['users'][0]['id'], expected)
            self.assertEqual(xray.normalize(normalized)[0], normalized)
            self.assertEqual(raw['outbounds'][0]['settings']['vnext'][0]['users'][0]['id'], identity)
        for identity in ['a' * 30, '界' * 10]:
            xray.normalize(fixture(identity=identity))
        for identity in ['', 'a' * 31, '界' * 11, 123, None]:
            with self.subTest(identity=identity), self.assertRaises(Fault):
                xray.normalize(fixture(identity=identity))

    def test_export_formats_normalize_without_changing_input(self):
        for port in [443, '443', ' 443 ']:
            raw = fixture(port)
            before = json.dumps(raw)
            config, address, actual_port, sni, insecure = xray.normalize(raw)
            self.assertEqual(actual_port, 443)
            self.assertEqual(sni, address)
            self.assertFalse(insecure)
            tunnel = config['outbounds'][0]
            self.assertEqual(tunnel['settings']['vnext'][0]['port'], 443)
            self.assertEqual(tunnel['streamSettings']['wsSettings']['headers']['Host'], 'ws.example.com')
            self.assertEqual(xray.normalize(config)[0], config)
            self.assertEqual(json.dumps(raw), before)

    def test_bad_ports_still_rejected(self):
        for port in [True, False, 443.5, 0, 65536, '0', '65536', '443.0', '4e2', '', None]:
            with self.subTest(port=port), self.assertRaises(Fault):
                xray.normalize(fixture(port))

    def test_browser_accepts_exports_and_names_invalid_field(self):
        source = (Path(__file__).resolve().parents[1] / 'backend/static/admin.js').read_text()
        start = source.index('function checkImport(value)')
        end = source.index("$('vless-template').onclick", start)
        script = source[start:end] + '''
const assert = require('node:assert/strict');
const fixture = JSON.parse(process.argv[1]);
assert.equal(checkImport(JSON.stringify(fixture)), 'VLESS');
const server = fixture.outbounds[0].settings.vnext[0];
for (const id of ['olise', '我爱🍉老师1314', 'a'.repeat(30), '界'.repeat(10)]) {
  server.users[0].id = id;
  assert.equal(checkImport(JSON.stringify(fixture)), 'VLESS');
}
for (const id of ['', 'a'.repeat(31), '界'.repeat(11), null, 123]) {
  server.users[0].id = id;
  assert.throws(() => checkImport(JSON.stringify(fixture)), /user ID/);
}
server.users[0].id = 'olise';
server.port = '65536';
assert.throws(() => checkImport(JSON.stringify(fixture)), /server port/);
server.port = 443; server.users[0].id = 'REPLACE_UUID';
assert.throws(() => checkImport(JSON.stringify(fixture)), /user ID/);
server.address = 'REPLACE_SERVER';
assert.throws(() => checkImport(JSON.stringify(fixture)), /server address/);
'''
        subprocess.run(['node', '-e', script, json.dumps(fixture())], check=True, capture_output=True)
