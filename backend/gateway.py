"""TPP/1: length-framed IP over authenticated TLS. No custom cryptography.

Pilot transport: TCP-over-TCP has throughput limitations; not Xray compatible.
Every IP packet is charged durably BEFORE forwarding, on both directions.
"""
import asyncio
import fcntl
import ipaddress
import json
import os
import ssl
import sqlite3
import struct

from .store import Fault

MTU = 1400


async def receive(reader, maximum=8192):
    length = struct.unpack('!I', await reader.readexactly(4))[0]
    if not 1 <= length <= maximum:
        raise Fault('Invalid tunnel frame')
    return await reader.readexactly(length)


async def send(writer, payload):
    writer.write(struct.pack('!I', len(payload)) + payload)
    await writer.drain()


def addresses(slot):
    base = int(ipaddress.IPv4Address('10.77.0.0')) + slot * 4
    return str(ipaddress.IPv4Address(base + 1)), str(ipaddress.IPv4Address(base + 2))


def valid_packet(packet, client, outgoing=True):
    if len(packet) < 20 or len(packet) > MTU or packet[0] >> 4 != 4:
        return False
    ihl = (packet[0] & 15) * 4
    if ihl < 20 or ihl > len(packet) or int.from_bytes(packet[2:4], 'big') != len(packet):
        return False
    source, destination = ipaddress.IPv4Address(packet[12:16]), ipaddress.IPv4Address(packet[16:20])
    if outgoing:
        return str(source) == client and destination.is_global and not destination.is_multicast
    return str(destination) == client and source.is_global and not source.is_multicast


class LinuxTun:
    def __init__(self, slot):
        self.fd = -1
        self.name = 'tpp' + str(slot)
        self.server, self.client = addresses(slot)

    async def start(self):
        self.fd = os.open('/dev/net/tun', os.O_RDWR | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, 0x400454ca, struct.pack('16sH', self.name.encode(), 0x0001 | 0x1000))
            await self.command('ip', 'address', 'add', self.server + '/30', 'dev', self.name)
            await self.command('ip', 'link', 'set', 'dev', self.name, 'mtu', str(MTU), 'up')
        except BaseException:
            self.close()
            raise

    async def command(self, *args):
        p = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        if await p.wait() != 0:
            raise Fault('Gateway network configuration failed', 503)

    async def ready(self, write=False):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        def done():
            if not future.done():
                future.set_result(None)
        add = loop.add_writer if write else loop.add_reader
        remove = loop.remove_writer if write else loop.remove_reader
        fd = self.fd
        add(fd, done)
        try:
            await future
        finally:
            remove(fd)

    async def read(self):
        while True:
            try:
                return os.read(self.fd, MTU)
            except BlockingIOError:
                await self.ready()

    async def write(self, packet):
        while True:
            try:
                if os.write(self.fd, packet) != len(packet):
                    raise Fault('Incomplete tunnel write', 503)
                return
            except BlockingIOError:
                await self.ready(True)

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


class Gateway:
    def __init__(self, store, tun_factory=LinuxTun):
        self.store, self.tun_factory = store, tun_factory
        self.server = None
        self.connections = set()
        self.admission = asyncio.Semaphore(256)
        self.context = None

    async def start(self, host, port, cert, key):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.options |= ssl.OP_NO_COMPRESSION
        context.load_cert_chain(cert, key)
        self.context = context
        def record_sni(connection, name, _):
            connection._tpp_sni = name or ''
        context.set_servername_callback(record_sni)
        self.server = await asyncio.start_server(self.handle, host, port, ssl=context, ssl_handshake_timeout=10, limit=16384)

    async def handle(self, reader, writer):
        session, tun, tasks = None, None, []
        task = asyncio.current_task()
        self.connections.add(task)
        try:
            if self.admission.locked():
                raise Fault('Gateway is busy', 503)
            async with self.admission:
                hello = json.loads(await asyncio.wait_for(receive(reader), 10))
                if not isinstance(hello, dict) or hello.get('protocol') != 'TPP/1':
                    raise Fault('Unsupported tunnel protocol')
                connection = writer.get_extra_info('ssl_object')
                ticket = hello.get('ticket', '')
                if not isinstance(ticket, str) or not 1 <= len(ticket) <= 100:
                    raise Fault('Invalid tunnel ticket', 401)
                session = self.store.open_tunnel(ticket, getattr(connection, '_tpp_sni', ''), connection.version())
                tun = self.tun_factory(session['slot'])
                await tun.start()
                await send(writer, json.dumps({'ok': True, 'address': tun.client, 'prefix': 30,
                                              'dns': '1.1.1.1', 'mtu': MTU, 'protocol': 'TPP/1'}).encode())
                lock = asyncio.Lock()
                async def transmit(body):
                    async with lock:
                        await asyncio.wait_for(send(writer, body), 15)
                async def upload():
                    while True:
                        frame = await asyncio.wait_for(receive(reader, MTU + 1), 45)
                        if frame[0] == 2 and len(frame) == 9:
                            await transmit(b'\x03' + frame[1:])
                        elif frame[0] == 1:
                            packet = frame[1:]
                            if not valid_packet(packet, tun.client):
                                continue  # IPv6/private destinations/spoofed addresses are dropped.
                            self.store.consume(session['id'], len(packet), 'up')
                            await tun.write(packet)
                        else:
                            raise Fault('Invalid packet type')
                async def download():
                    while True:
                        packet = await tun.read()
                        if not valid_packet(packet, tun.client, False):
                            continue
                        self.store.consume(session['id'], len(packet), 'down')
                        await transmit(b'\x01' + packet)
                async def enforce():
                    while True:
                        await asyncio.sleep(1)
                        self.store.consume(session['id'])
                tasks = [asyncio.create_task(f()) for f in [upload, download, enforce]]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for finished in done:
                    finished.result()
        except Fault as error:
            try:
                if session:
                    await asyncio.wait_for(send(writer, b'\x04' + error.message.encode()), 2)
                else:
                    await asyncio.wait_for(send(writer, json.dumps({'ok': False, 'error': error.message}).encode()), 2)
            except Exception:
                pass
        except (asyncio.IncompleteReadError, ConnectionError, TimeoutError, ValueError, OSError):
            pass
        except sqlite3.Error:
            pass  # Fail closed if durable account/usage storage is unavailable.
        finally:
            for child in tasks:
                child.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if tun:
                tun.close()
            if session:
                self.store.close_tunnel(session['id'])
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, TimeoutError):
                pass
            self.connections.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for task in list(self.connections):
            task.cancel()
        await asyncio.gather(*list(self.connections), return_exceptions=True)
