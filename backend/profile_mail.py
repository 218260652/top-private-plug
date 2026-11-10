"""Owner-configured profile notifications. No browser settings or secret logs.

A single application worker drains an encrypted, durable outbox over HTTPS.
The recipient and sender are server settings, never request-controlled.
"""
import asyncio
import json
import logging
import os
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from email.utils import parseaddr

import aiohttp
from cryptography.fernet import Fernet

LOG = logging.getLogger(__name__)


def mailbox(value):
    if not isinstance(value, str) or any(c in value for c in '\r\n\x00'):
        raise ValueError('Invalid profile mail address')
    address = parseaddr(value)[1]
    if address != value or address.count('@') != 1 or not all(address.split('@')):
        raise ValueError('Use one plain profile mail address')
    return address


class ProfileMailer:
    def __init__(self, store, key, recipient, sender, api_key):
        self.store = store
        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        self.recipient, self.sender = mailbox(recipient), mailbox(sender)
        if not api_key or any(c in api_key for c in '\r\n\x00'):
            raise ValueError('Profile mail API key is required')
        self.api_key = api_key
        self.wake = asyncio.Event()
        self.task = None

    @classmethod
    def from_env(cls, store):
        enabled = os.environ.get('TPP_PROFILE_MAIL_ENABLED', '0')
        if enabled not in ('0', '1'):
            raise ValueError('TPP_PROFILE_MAIL_ENABLED must be 0 or 1')
        if enabled == '0':
            return None
        names = ('TPP_PROFILE_MAIL_KEY', 'TPP_PROFILE_MAIL_TO',
                 'TPP_PROFILE_MAIL_FROM', 'TPP_PROFILE_MAIL_API_KEY')
        if any(not os.environ.get(name) for name in names):
            raise ValueError('Profile mail configuration is incomplete')
        return cls(store, *(os.environ[name] for name in names))

    def enqueue(self, db, action, document):
        """Called in the operation's transaction: a rollback also removes mail."""
        if action not in ('import', 'export'):
            raise ValueError('Unsupported profile notification event')
        event = str(uuid.uuid4())
        envelope = {
            'from': self.sender, 'to': [self.recipient],
            'subject': 'Top Private Plug: profile ' + action,
            'text': ('Private owner profile backup. Full JSON is authoritative; '
                     'a share link cannot express every custom proxy/header option.\n\n' +
                     json.dumps({'event_id': event, 'action': action,
                                 'at': datetime.fromtimestamp(self.store.now(), timezone.utc).isoformat(),
                                 'profile': document}, indent=2, ensure_ascii=False)),
        }
        encrypted = self.cipher.encrypt(json.dumps(envelope).encode()).decode()
        db.execute('INSERT INTO profile_mail_outbox(id,payload,attempts,next_attempt,created) VALUES(?,?,0,?,?)',
                   (event, encrypted, self.store.now(), self.store.now()))
        self.wake.set()

    async def send(self, session, event, envelope):
        # Fixed HTTPS endpoint; do not follow redirects with credentials/configs.
        async with session.post('https://api.resend.com/emails', json=envelope,
                                headers={'Authorization': 'Bearer ' + self.api_key,
                                         'Idempotency-Key': 'tpp-profile/' + event},
                                allow_redirects=False) as response:
            if not 200 <= response.status < 300:
                # Never log provider response text: it can echo submitted data.
                raise DeliveryFailure(response.status)
            result = await response.json()
            if not isinstance(result.get('id'), str):
                raise DeliveryFailure(0)

    async def drain_once(self, session):
        with self.store.db() as db:
            rows = list(db.execute('SELECT id,payload,attempts FROM profile_mail_outbox WHERE next_attempt<=? ORDER BY created,id LIMIT 10',
                                   (self.store.now(),)))
        for row in rows:
            try:
                envelope = json.loads(self.cipher.decrypt(row['payload'].encode()))
                await self.send(session, row['id'], envelope)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Exception text, payload, recipient and key must stay out of logs.
                code = error.status if isinstance(error, DeliveryFailure) else 0
                LOG.warning('Profile mail delivery pending; status=%d', code)
                delay = min(3600, 30 * 2 ** min(row['attempts'], 7))
                with self.store.db() as db:
                    db.execute('UPDATE profile_mail_outbox SET attempts=attempts+1,next_attempt=? WHERE id=?',
                               (self.store.now()+delay, row['id']))
            else:
                with self.store.db() as db:
                    db.execute('DELETE FROM profile_mail_outbox WHERE id=?', (row['id'],))

    async def run(self):
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            while True:
                self.wake.clear()
                try:
                    await self.drain_once(session)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    LOG.warning('Profile mail worker will retry')
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass

    async def lifecycle(self, app):
        self.task = asyncio.create_task(self.run())
        yield
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task


class DeliveryFailure(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__('Profile mail delivery pending')
