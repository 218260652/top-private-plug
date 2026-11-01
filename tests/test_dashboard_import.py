"""Run the dashboard's actual import gate without requiring a browser session."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from tests import test_xray


@unittest.skipUnless(shutil.which('node'), 'Node.js required')
class DashboardImportTests(unittest.TestCase):
    def test_websocket_and_tcp_pass_browser_gate_but_unsupported_transport_fails(self):
        source = (Path(__file__).resolve().parents[1] / 'backend/static/admin.js').read_text()
        gate = source.split('function checkImport(value) {', 1)[1].split("$('vless-template').onclick", 1)[0]
        raw = test_xray.XrayTests.vless_config()
        script = 'function checkImport(value) {' + gate + '\nconst raw = ' + json.dumps(raw) + ''';
        const check = () => checkImport(JSON.stringify(raw));
        if (check() !== 'VLESS') throw Error('TCP regression');
        raw.outbounds[0].streamSettings.network = 'ws';
        raw.outbounds[0].streamSettings.wsSettings = {path:'/baron',headers:{Host:'ws.example.com'}};
        if (check() !== 'VLESS') throw Error('WebSocket rejected');
        raw.outbounds[0].streamSettings.network = 'grpc';
        let rejected = false;
        try {check();} catch (error) {rejected = true;}
        if (!rejected) throw Error('Unsupported transport accepted');
        raw.outbounds[0].streamSettings.network = 'ws';
        raw.outbounds[0].streamSettings.wsSettings.path = 'missing-slash';
        rejected = false;
        try {check();} catch (error) {rejected = true;}
        if (!rejected) throw Error('Malformed WebSocket path accepted');
        '''
        subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True, timeout=10)
