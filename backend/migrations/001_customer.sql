CREATE TABLE IF NOT EXISTS customer_users (
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password TEXT NOT NULL,
 name TEXT NOT NULL, notes TEXT NOT NULL, state TEXT NOT NULL,
 created BIGINT NOT NULL, starts BIGINT NOT NULL, expires BIGINT NOT NULL,
 device_limit INTEGER NOT NULL CHECK(device_limit BETWEEN 1 AND 50),
 must_change INTEGER NOT NULL, last_login BIGINT,
 account_type TEXT NOT NULL DEFAULT 'paid' CHECK(account_type IN ('paid','trial'))
);
CREATE TABLE IF NOT EXISTS customer_devices (
 id TEXT PRIMARY KEY, customer TEXT NOT NULL REFERENCES customer_users(id),
 public_key TEXT NOT NULL, created BIGINT NOT NULL, seen BIGINT NOT NULL,
 revoked INTEGER NOT NULL DEFAULT 0, UNIQUE(customer,public_key)
);
CREATE TABLE IF NOT EXISTS customer_sessions (
 id TEXT PRIMARY KEY, device TEXT NOT NULL REFERENCES customer_devices(id),
 access TEXT NOT NULL UNIQUE, access_until BIGINT NOT NULL, expires BIGINT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS customer_refresh (
 hash TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES customer_sessions(id),
 used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS customer_events (
 id TEXT PRIMARY KEY, at BIGINT NOT NULL, actor TEXT NOT NULL,
 subject TEXT NOT NULL, action TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS customer_events_at ON customer_events(at);
CREATE TABLE IF NOT EXISTS customer_attempts (
 bucket TEXT PRIMARY KEY, started BIGINT NOT NULL, count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_networks (
 carrier TEXT PRIMARY KEY, profile TEXT NOT NULL REFERENCES profiles(id), tested INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS customer_leases (
 hash TEXT PRIMARY KEY, device TEXT NOT NULL UNIQUE REFERENCES customer_devices(id),
 session TEXT NOT NULL REFERENCES customer_sessions(id), carrier TEXT NOT NULL,
 profile TEXT NOT NULL REFERENCES profiles(id), version INTEGER NOT NULL, expires BIGINT NOT NULL, seen BIGINT
);
CREATE TABLE IF NOT EXISTS customer_plans (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, days INTEGER NOT NULL, price_cents INTEGER NOT NULL
);
