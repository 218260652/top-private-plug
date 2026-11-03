# Owner profile import/export notifications

This server-only feature has no dashboard fields, buttons, banners or delivery-status responses. Normal admin state still excludes connection secrets. The recipient is configured on the server and cannot be overridden by an import or export request.

## Events and contents

A successful import or replacement through the authenticated admin API queues an email in the same database transaction. Its body includes the supplied unlocked JSON, the normalized saved JSON, the generated VLESS link when applicable, profile name, carrier, ID, version and UTC event time. Invalid imports do not send notifications. Encrypted/locked supplier formats are not decrypted by this feature.

`POST /admin/api/xray-profiles/{id}/export` with JSON `{}` returns the stored configuration and a VLESS link, and queues an export email. It requires the existing admin session, correct Origin, and `X-TPP-Request: 1`. No export button is added. Client connections and profile-list reads are not admin exports and do not send emails. Only operations through this server are observed.

Full JSON is authoritative: standard VLESS links cannot represent arbitrary custom headers and upstream proxy chains. Original input is included in import emails, including any fields the normalizer does not retain. Export emails contain exactly the stored configuration.

## Private server configuration

Use Render Environment settings; never put these values in frontend code, chat, source control or logs:

| Variable | Value |
| --- | --- |
| `TPP_PROFILE_MAIL_ENABLED` | `1` after all settings are complete; defaults to `0` |
| `TPP_PROFILE_MAIL_TO` | Owner's single receiving email address |
| `TPP_PROFILE_MAIL_FROM` | A sender address permitted by the owner's Resend account |
| `TPP_PROFILE_MAIL_API_KEY` | A sending API key from that account |
| `TPP_PROFILE_MAIL_KEY` | A persistent Fernet key for the encrypted queue |

Generate the encryption key privately using `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. Keep it stable across deploys and backed up securely. Replacing it makes existing queued messages unreadable; the worker retains and retries those rows instead of logging or discarding their contents.

Render's free web service blocks SMTP ports 25/465/587, so delivery uses Resend's fixed HTTPS API endpoint with TLS certificate checking and redirects disabled. Provider credentials are still required; connecting Gmail in ChatGPT does not authorize this server to send mail.

Enable only when the receiving account is controlled by the service owner. Bodies intentionally contain reusable VPN secrets. There is no recipient value accepted from API callers and no public endpoint for inspecting the queue. The owner's private source and server settings document the feature; it is not concealed from code review or server administration.

## Delivery behavior and checks

Payloads are Fernet encrypted in `profile_mail_outbox`, using the existing persistent PostgreSQL database on Render. A background worker sends them without waiting in the import/export response. Failed sends stay queued with exponential backoff capped at one hour; a restart resumes pending messages. Successful provider acceptance removes the queued payload. Import/export and queue insertion commit or roll back together.

Each event has a stable provider idempotency key. Delivery is at least once: a crash after provider acceptance but before database deletion can cause a duplicate beyond the provider's idempotency window. Provider acceptance is not proof of inbox delivery; mail can still bounce or enter spam. Render can sleep, so pending retries may wait until the service wakes.

Errors log only a generic status code. Keys, JSON bodies, VLESS credentials and provider response text never enter notification logs. A single worker is required, matching the server's existing single-process lock.

`python -m unittest tests.test_profile_mail -v` covers transactional import/replacement/export events, encrypted persistence/restarts, retry and success cleanup, log redaction, fixed HTTPS transport, recipient injection rejection, admin authorization, CSRF and unchanged frontend responses. `tools/verify_postgres.py` additionally runs queue regression tests in a temporary isolated PostgreSQL schema before deployment migration. None of these fixture tests sends real email.

Before calling delivery active, configure the server, deploy, import a non-sensitive test profile and export it, then confirm both emails actually arrive at the owner's address. Do not claim live email delivery from mock-test success.

References: https://render.com/docs/free and https://resend.com/docs/api-reference/emails/send-email
