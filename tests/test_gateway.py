import asyncio
import datetime
import ipaddress
import json
import ssl
import struct
import tempfile
import unittest
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from backend.gateway import Gateway, addresses, receive, send, valid_packet
from backend.store import Store
from tests.test_control import device, proof


def packet(source, destination, size=40):
    b=bytearray(size);b[0]=0x45;b[2:4]=size.to_bytes(2,'big');b[8]=64;b[9]=17
    b[12:16]=ipaddress.IPv4Address(source).packed;b[16:20]=ipaddress.IPv4Address(destination).packed
    return bytes(b)


class FakeTun:
    """Test packet device, deliberately NOT a real Linux TUN or internet route."""
    def __init__(self,slot):
        self.server,self.client=addresses(slot);self.queue=asyncio.Queue()
    async def start(self):pass
    async def read(self):return await self.queue.get()
    async def write(self,p):await self.queue.put(packet(str(ipaddress.IPv4Address(p[16:20])),self.client,len(p)))
    def close(self):pass


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.clock=[1_800_000_000];self.store=Store(self.base/'gateway.sqlite3',lambda:self.clock[0])
        key=ec.generate_private_key(ec.SECP256R1());name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'vpn.test')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('vpn.test')]),False).sign(key,hashes.SHA256())
        (self.base/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM));(self.base/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        self.gateway=Gateway(self.store,FakeTun);await self.gateway.start('127.0.0.1',0,str(self.base/'cert.pem'),str(self.base/'key.pem'))
        self.port=self.gateway.server.sockets[0].getsockname()[1]
        self.profile=self.store.save_profile({'name':'Test','carrier':'MTN','server':'127.0.0.1','port':self.port,'sni':'vpn.test','tls_min':'1.2','enabled':True})
        self.private,self.public=device();self.writers=[]

    async def asyncTearDown(self):
        for w in self.writers:w.close()
        await self.gateway.close();self.tmp.cleanup()

    async def connect(self,quota=10000,duration=3600):
        item=self.store.issue({'label':'Test','kind':'trial','duration_seconds':duration,'quota_bytes':quota,'profile_ids':[self.profile['id']]})
        a=self.store.activate(dict(proof(self.store,self.private,self.public,'activate'),code=item['code']));self.account_id=a['account']['id']
        t=self.store.connect(a['token'],dict(proof(self.store,self.private,self.public,'connect'),profile_id=self.profile['id']))
        ctx=ssl.create_default_context(cafile=str(self.base/'cert.pem'))
        reader,writer=await asyncio.open_connection('127.0.0.1',self.port,ssl=ctx,server_hostname='vpn.test');self.writers.append(writer)
        await send(writer,json.dumps({'protocol':'TPP/1','ticket':t['ticket']}).encode())
        hello=json.loads(await receive(reader));self.assertTrue(hello['ok']);return reader,writer,hello

    async def test_tls_handshake_packet_roundtrip_and_real_accounting(self):
        r,w,h=await self.connect();self.assertIn(w.get_extra_info('ssl_object').version(),['TLSv1.2','TLSv1.3'])
        await send(w,b'\x01'+packet(h['address'],'1.1.1.1'))
        reply=await asyncio.wait_for(receive(r),2);self.assertEqual(reply[0],1);self.assertTrue(valid_packet(reply[1:],h['address'],False))
        self.assertEqual(self.store.account(self.account_id)['used'],80)
        await send(w,b'\x02'+struct.pack('!Q',123));self.assertEqual(await receive(r),b'\x03'+struct.pack('!Q',123))

    async def test_quota_enforced_by_gateway(self):
        r,w,h=await self.connect(quota=60);await send(w,b'\x01'+packet(h['address'],'1.1.1.1'))
        reply=await asyncio.wait_for(receive(r),2);self.assertEqual(reply[0],4);self.assertIn(b'exhausted',reply)
        self.assertEqual(self.store.account(self.account_id)['used'],40)

    async def test_admin_suspension_cuts_idle_connection(self):
        r,w,h=await self.connect();self.store.update_account(self.account_id,{'suspended':True})
        reply=await asyncio.wait_for(receive(r),2);self.assertEqual(reply[0],4);self.assertIn(b'disabled',reply)

    async def test_expiry_cuts_connection_without_phone_clock(self):
        r,w,h=await self.connect();self.clock[0]+=3600
        reply=await asyncio.wait_for(receive(r),2);self.assertIn(b'expired',reply)

    async def test_spoofed_and_private_destinations_dropped(self):
        r,w,h=await self.connect()
        await send(w,b'\x01'+packet('10.77.0.99','1.1.1.1'))
        await send(w,b'\x01'+packet(h['address'],'169.254.169.254'))
        await send(w,b'\x02'+struct.pack('!Q',12));self.assertEqual((await receive(r))[0],3)
        self.assertEqual(self.store.account(self.account_id)['used'],0)

    async def test_invalid_ticket_rejected(self):
        ctx=ssl.create_default_context(cafile=str(self.base/'cert.pem'))
        r,w=await asyncio.open_connection('127.0.0.1',self.port,ssl=ctx,server_hostname='vpn.test');self.writers.append(w)
        await send(w,json.dumps({'protocol':'TPP/1','ticket':'invalid'}).encode());self.assertFalse(json.loads(await receive(r))['ok'])

    async def test_untrusted_server_certificate_rejected(self):
        loop=asyncio.get_running_loop();previous=loop.get_exception_handler();loop.set_exception_handler(lambda loop,context:None)
        with self.assertRaises(ssl.SSLCertVerificationError):
            await asyncio.open_connection('127.0.0.1',self.port,ssl=ssl.create_default_context(),server_hostname='vpn.test')
        await asyncio.sleep(.05);loop.set_exception_handler(previous)

    def test_packet_validation_rejects_ipv6_and_truncation(self):
        self.assertFalse(valid_packet(b'\x60'+b'\0'*39,'10.77.0.6'))
        self.assertFalse(valid_packet(packet('10.77.0.6','1.1.1.1')[:-1],'10.77.0.6'))
