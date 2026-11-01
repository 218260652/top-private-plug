"""Restricted VLESS/Trojan imports and expiring app leases."""
import copy
import ipaddress
import json
import re
import secrets
import uuid
from .store import Fault, digest


def host(value):
    if not isinstance(value, str) or len(value) > 253:
        raise Fault('Invalid server hostname')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', value):
            raise Fault('Invalid server hostname')
    return value


def port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise Fault('Invalid server port')
    return value


def normalize(raw, allow_insecure=False):
    """Rebuild only supported fields; never accept file paths, APIs or listeners."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raise Fault('Paste unlocked Xray JSON, not a NetMod encrypted link') from None
    if not isinstance(raw, dict):
        raise Fault('Xray JSON object required')
    source = raw.get('outbounds', [])
    if not isinstance(source, list):
        raise Fault('Outbounds must be an array')
    tunnels = [o for o in source if isinstance(o, dict) and o.get('protocol') in ('vless', 'trojan')]
    if len(tunnels) != 1:
        raise Fault('Import one VLESS or Trojan outbound per profile')
    original = tunnels[0]
    protocol = original['protocol']
    try:
        servers = original['settings']['vnext' if protocol == 'vless' else 'servers']
        if not isinstance(servers, list) or len(servers) != 1:
            raise Fault('Import exactly one tunnel server')
        server = servers[0]
        address, server_port = host(server['address']), port(server['port'])
        if protocol == 'vless':
            users = server['users']
            if not isinstance(users, list) or len(users) != 1:
                raise Fault('Import exactly one VLESS user')
            user = users[0]
            identity = user['id']
            if not isinstance(identity, str):
                raise Fault('VLESS UUID is required')
            try:
                identity = str(uuid.UUID(identity))
            except ValueError:
                raise Fault('VLESS UUID is invalid') from None
            if user.get('encryption', 'none') != 'none' or user.get('flow', ''):
                raise Fault('Only VLESS encryption none without flow is supported')
            settings = {'vnext': [{'address': address, 'port': server_port,
                'users': [{'id': identity, 'encryption': 'none', 'level': 0}]}]}
        else:
            password = server['password']
            if not isinstance(password, str) or not 1 <= len(password) <= 256:
                raise Fault('Trojan password is required')
            settings = {'servers': [{'address': address, 'port': server_port, 'password': password, 'level': 0}]}
        stream = original['streamSettings']
        network = stream.get('network', 'tcp')
        if network not in ('tcp', 'raw', 'ws') or stream.get('security') != 'tls':
            raise Fault('This importer supports VLESS or Trojan over TCP or WebSocket with TLS')
        tls = stream.get('tlsSettings', {})
        sni = host(tls.get('serverName') or address)
        insecure = tls.get('allowInsecure', False)
        if type(insecure) is not bool:
            raise Fault('allowInsecure must be boolean')
        if insecure and not allow_insecure:
            raise Fault('This profile disables certificate checks. Enable the testing option explicitly or supply a verified profile.')
        # Keep the historical statistics tag for installed 0.1.5 clients.
        # The tag is an internal identifier, not the tunnel protocol.
        outbound = {'tag': 'trojan', 'protocol': protocol, 'settings': settings,
            'streamSettings': {'network': 'ws' if network == 'ws' else 'tcp', 'security': 'tls', 'tlsSettings': {
                'serverName': sni, 'allowInsecure': insecure, 'minVersion': '1.2'}}}
        if network == 'ws':
            ws = stream.get('wsSettings', {})
            if not isinstance(ws, dict):
                raise Fault('Invalid WebSocket settings')
            path = ws.get('path', '/')
            if not isinstance(path, str) or not path.startswith('/') or len(path) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in path):
                raise Fault('WebSocket path must start with / and contain no control characters')
            headers = ws.get('headers', {})
            if not isinstance(headers, dict) or len(headers) > 20:
                raise Fault('Invalid WebSocket headers')
            for key, value in headers.items():
                if not isinstance(key, str) or not isinstance(value, str) or not re.fullmatch(r'[!#$%&\'*+.^_`|~0-9A-Za-z-]+', key) or len(value) > 1024 or any(ord(c) < 32 or ord(c) == 127 for c in value):
                    raise Fault('Invalid WebSocket header')
            headers = copy.deepcopy(headers)
            ws_host = ws.get('host')
            if ws_host is not None:
                if not isinstance(ws_host, str) or not ws_host or len(ws_host) > 1024 or any(ord(c) < 33 or ord(c) == 127 for c in ws_host):
                    raise Fault('Invalid WebSocket Host')
                if any(key.lower() == 'host' and value != ws_host for key, value in headers.items()):
                    raise Fault('Conflicting WebSocket Host values')
                headers = {key: value for key, value in headers.items() if key.lower() != 'host'}
                headers['Host'] = ws_host
            outbound['streamSettings']['wsSettings'] = {'path': path, 'headers': headers}
        fingerprint = tls.get('fingerprint')
        if fingerprint is not None:
            if fingerprint not in ('chrome', 'firefox', 'safari', 'edge', 'ios', 'android', 'random', 'randomized'):
                raise Fault('Unsupported TLS fingerprint')
            outbound['streamSettings']['tlsSettings']['fingerprint'] = fingerprint
        outbounds = [outbound]
        legacy_proxy = original.get('proxySettings')
        sockopt = stream.get('sockopt', {})
        if not isinstance(sockopt, dict):
            raise Fault('Invalid stream socket settings')
        tag = sockopt.get('dialerProxy')
        if legacy_proxy is not None:
            if not isinstance(legacy_proxy, dict):
                raise Fault('Invalid legacy proxy settings')
            legacy_tag = legacy_proxy['tag']
            if tag is not None and tag != legacy_tag:
                raise Fault('Conflicting upstream proxy tags')
            tag = legacy_tag
        if tag is not None:
            if not isinstance(tag, str) or not 1 <= len(tag) <= 100:
                raise Fault('Invalid upstream proxy tag')
            proxies = [o for o in source if isinstance(o, dict) and o.get('tag') == tag and o.get('protocol') == 'http']
            if len(proxies) != 1:
                raise Fault('The upstream must be one HTTP proxy')
            proxy = proxies[0]['settings']
            upstream = proxy['servers'][0]
            headers = proxy.get('headers', {})
            if not isinstance(headers, dict) or len(headers) > 20:
                raise Fault('Invalid HTTP headers')
            for key, value in headers.items():
                if not isinstance(key, str) or not isinstance(value, str) or not re.fullmatch(r'[!#$%&\'*+.^_`|~0-9A-Za-z-]+', key) or any(c in value for c in '\r\n\x00') or len(value) > 1024:
                    raise Fault('Invalid HTTP header')
            outbounds.append({'tag': 'http-upstream', 'protocol': 'http', 'settings': {
                'servers': [{'address': host(upstream['address']), 'port': port(upstream['port'])}],
                'headers': copy.deepcopy(headers)}})
            # The pinned Xray core rejects outbound proxySettings. TLS must be
            # dialed through the HTTP CONNECT proxy via the current sockopt field.
            outbound['streamSettings']['sockopt'] = {'dialerProxy': 'http-upstream'}
        dns = raw.get('dns', {}).get('servers', ['1.1.1.1'])
        if not isinstance(dns, list) or not 1 <= len(dns) <= 4:
            raise Fault('Use one to four DNS server addresses')
        for address_value in dns:
            if not isinstance(address_value, str):
                raise Fault('Use DNS server strings')
            # Permit the supplied routed DoH resolvers, never local-mode URLs.
            if address_value in ('https://1.1.1.1/dns-query', 'https://dns.google/dns-query'):
                continue
            # Restrict to literal addresses; no files, local socket paths or arbitrary URLs.
            try:
                ipaddress.ip_address(address_value.removeprefix('tcp+local://').removeprefix('tcp://'))
            except ValueError:
                raise Fault('Use literal DNS IPs, TCP DNS, or the supported Cloudflare/Google HTTPS resolvers') from None
        # Local-mode DNS bypasses Xray routing. Keep the resolver and TCP transport,
        # but dispatch queries through dns-in and the Trojan outbound instead.
        dns = ['tcp://' + value[len('tcp+local://'):] if value.startswith('tcp+local://') else value
               for value in dns]
    except (KeyError, IndexError, TypeError, AttributeError):
        raise Fault('Incomplete VLESS, Trojan or upstream settings') from None
    outbounds.extend([{'tag': 'dns-out', 'protocol': 'dns'}, {'tag': 'block', 'protocol': 'blackhole'}])
    config = {'log': {'loglevel': 'none'}, 'dns': {'servers': dns, 'queryStrategy': 'UseIPv4', 'tag': 'dns-in'},
        # Android supplies the descriptor. A nonempty name prevents Xray's
        # desktop auto-name path from calling net.Interfaces(), denied by Android.
        'inbounds': [{'tag': 'tun-inbound', 'protocol': 'tun', 'settings': {'name': 'tpp0', 'mtu': 1400}}],
        'outbounds': outbounds, 'stats': {},
        'policy': {'system': {'statsOutboundUplink': True, 'statsOutboundDownlink': True}},
        'routing': {'domainStrategy': 'AsIs', 'rules': [
            {'type': 'field', 'ip': ['224.0.0.0/4', 'ff00::/8'], 'outboundTag': 'block'},
            {'type': 'field', 'inboundTag': ['tun-inbound'], 'port': '53', 'network': 'tcp,udp', 'outboundTag': 'dns-out'},
            {'type': 'field', 'inboundTag': ['tun-inbound', 'dns-in'], 'network': 'tcp,udp', 'outboundTag': 'trojan'}]}}
    return config, server['address'], server_port, sni, insecure


def metadata(db, profiles):
    imports = {r['profile']: r['insecure'] for r in db.execute('SELECT profile,insecure FROM xray_profiles')}
    for profile in profiles:
        profile['engine'] = 'xray' if profile['id'] in imports else 'tpp'
        profile['insecure_tls'] = bool(imports.get(profile['id'], 0))
        profile['enforcement'] = 'app-reported' if profile['engine'] == 'xray' else 'gateway'
    return profiles


def save(store, data, profile_id=None):
    allow = data.get('allow_insecure', False)
    if type(allow) is not bool or type(data.get('enabled', True)) is not bool:
        raise Fault('Testing and enabled options must be boolean')
    config, address, server_port, sni, insecure = normalize(data.get('config'), allow)
    name, carrier = data.get('name', ''), data.get('carrier')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or carrier not in ['MTN', 'Telkom', 'Cell C', 'Any']:
        raise Fault('Provide a profile name and network label')
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        if profile_id:
            if not db.execute('SELECT 1 FROM xray_profiles WHERE profile=?', (profile_id,)).fetchone():
                raise Fault('Imported profile not found', 404)
            db.execute('UPDATE profiles SET name=?,carrier=?,server=?,port=?,sni=?,enabled=?,version=version+1 WHERE id=?',
                (name.strip(), carrier, address, server_port, sni, int(data.get('enabled', True)), profile_id))
            db.execute('UPDATE xray_profiles SET config=?,insecure=? WHERE profile=?', (json.dumps(config), int(insecure), profile_id))
        else:
            profile_id = str(uuid.uuid4())
            db.execute('INSERT INTO profiles(id,name,carrier,server,port,sni,tls_min,enabled) VALUES(?,?,?,?,?,?,?,?)',
                (profile_id, name.strip(), carrier, address, server_port, sni, '1.2', int(data.get('enabled', True))))
            db.execute('INSERT INTO xray_profiles(profile,config,insecure) VALUES(?,?,?)', (profile_id, json.dumps(config), int(insecure)))
        store.audit(db, 'xray_profile_imported', profile_id)
    return store.get_profile(profile_id)


def connect(store, token, data):
    account = store.client_auth(token)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM accounts WHERE id=?', (account['id'],)).fetchone()
        store.require_active(row)
        device_key = account['auth_device_key']
        store.proof(db, data, device_key, 'connect')
        p = db.execute('SELECT * FROM profiles WHERE id=? AND enabled=1', (data.get('profile_id', ''),)).fetchone()
        if not p or p['id'] not in json.loads(row['profiles']):
            raise Fault('This connection profile is unavailable', 403)
        x = db.execute('SELECT config,insecure FROM xray_profiles WHERE profile=?', (p['id'],)).fetchone()
        if not x:
            raise Fault('Imported profile not found', 404)
        config = normalize(json.loads(x['config']), allow_insecure=bool(x['insecure']))[0]
        active = db.execute('SELECT 1 FROM sessions WHERE account=? AND seen>?', (row['id'], store.now()-30)).fetchone()
        if row['kind'] == 'trial':
            active_x = db.execute('SELECT 1 FROM trial_xray_sessions WHERE account=? AND device_key=? AND seen>?',
                                  (row['id'], device_key, store.now()-30)).fetchone()
        else:
            active_x = db.execute('SELECT 1 FROM xray_sessions WHERE account=? AND seen>?',
                                  (row['id'], store.now()-30)).fetchone()
        if active or active_x:
            raise Fault('Device already connected; disconnect first', 409)
        lease = secrets.token_urlsafe(32)
        if row['kind'] == 'trial':
            # Other trial devices retain their own live sessions and leases.
            db.execute('DELETE FROM trial_xray_sessions WHERE account=? AND device_key=?', (row['id'], device_key))
            db.execute('INSERT INTO trial_xray_sessions(account,device_key,profile,version,lease,seen,up,down) VALUES(?,?,?,?,?,?,0,0)',
                       (row['id'], device_key, p['id'], p['version'], digest(lease), store.now()))
        else:
            db.execute('DELETE FROM tickets WHERE account=?', (row['id'],))
            db.execute('DELETE FROM xray_sessions WHERE account=?', (row['id'],))
            db.execute('INSERT INTO xray_sessions(account,profile,version,lease,seen,up,down) VALUES(?,?,?,?,?,0,0)',
                       (row['id'], p['id'], p['version'], digest(lease), store.now()))
        profile = metadata(db, [dict(p)])[0]
    return {'engine': 'xray', 'profile': profile, 'config': config, 'lease': lease, 'lease_seconds': 30}


def heartbeat(store, token, data):
    account = store.client_auth(token)
    lease = data.get('lease')
    if not isinstance(lease, str) or not 1 <= len(lease) <= 128:
        raise Fault('Connection lease required')
    up, down = data.get('up'), data.get('down')
    if any(type(v) is not int or not 0 <= v <= 2**53 for v in [up, down]):
        raise Fault('Invalid byte counters')
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM accounts WHERE id=?', (account['id'],)).fetchone()
        store.require_active(row)
        if row['kind'] == 'trial':
            session = db.execute('SELECT * FROM trial_xray_sessions WHERE account=? AND device_key=? AND lease=?',
                                 (row['id'], account['auth_device_key'], digest(lease))).fetchone()
        else:
            session = db.execute('SELECT * FROM xray_sessions WHERE account=? AND lease=?',
                                 (row['id'], digest(lease))).fetchone()
        if not session or session['seen'] <= store.now()-30:
            raise Fault('Connection lease expired; reconnect', 403)
        p = db.execute('SELECT * FROM profiles WHERE id=?', (session['profile'],)).fetchone()
        if not p or not p['enabled'] or p['version'] != session['version'] or p['id'] not in json.loads(row['profiles']):
            raise Fault('Profile changed; reconnect', 403)
        if up < session['up'] or down < session['down']:
            raise Fault('Byte counters must not decrease')
        delta_up, delta_down = up-session['up'], down-session['down']
        if row['kind'] == 'trial':
            # Serialized with the account lock: a shared quota cannot be credited
            # more than once, even when many devices report usage concurrently.
            charge = min(delta_up + delta_down, row['quota'] - row['used'])
            charge_up = min(delta_up, charge)
            charge_down = charge - charge_up
            db.execute('UPDATE accounts SET used=used+? WHERE id=?', (charge, row['id']))
            db.execute('UPDATE trial_xray_sessions SET up=?,down=?,seen=? WHERE account=? AND device_key=?',
                       (up, down, store.now(), row['id'], account['auth_device_key']))
            if charge:
                db.execute('INSERT INTO usage(account,at,up,down) VALUES(?,?,?,?) ON CONFLICT(account,at) DO UPDATE SET up=up+excluded.up,down=down+excluded.down',
                           (row['id'], store.now()//60*60, charge_up, charge_down))
            allowed = row['used'] + charge < row['quota'] and charge == delta_up + delta_down
        else:
            # Paid accounting is unchanged.
            db.execute('UPDATE accounts SET used=used+? WHERE id=?', (delta_up+delta_down, row['id']))
            db.execute('UPDATE xray_sessions SET up=?,down=?,seen=? WHERE account=?', (up, down, store.now(), row['id']))
            db.execute('INSERT INTO usage(account,at,up,down) VALUES(?,?,?,?) ON CONFLICT(account,at) DO UPDATE SET up=up+excluded.up,down=down+excluded.down',
                       (row['id'], store.now()//60*60, delta_up, delta_down))
            allowed = row['used']+delta_up+delta_down < row['quota']
    if not allowed:
        raise Fault('Data allowance exhausted', 403)
    return {'ok': True, 'lease_seconds': 30, 'enforcement': 'app-reported'}


def disconnect(store, token, data):
    account = store.client_auth(token)
    lease = data.get('lease')
    if not isinstance(lease, str):
        raise Fault('Connection lease required')
    with store.db() as db:
        if account['kind'] == 'trial':
            db.execute('DELETE FROM trial_xray_sessions WHERE account=? AND device_key=? AND lease=?',
                       (account['id'], account['auth_device_key'], digest(lease)))
        else:
            db.execute('DELETE FROM xray_sessions WHERE account=? AND lease=?', (account['id'], digest(lease)))
    return {'ok': True}


def toggle(store, profile_id, data):
    if set(data) != {'enabled'} or type(data['enabled']) is not bool:
        raise Fault('Provide enabled as a boolean')
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM xray_profiles WHERE profile=?', (profile_id,)).fetchone():
            raise Fault('Imported profile not found', 404)
        db.execute('UPDATE profiles SET enabled=?,version=version+1 WHERE id=?', (int(data['enabled']), profile_id))
        store.audit(db, 'xray_profile_enabled' if data['enabled'] else 'xray_profile_disabled', profile_id)
    return store.get_profile(profile_id)



