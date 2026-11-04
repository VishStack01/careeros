-- Plans, billing and AI usage. Portable SQL for SQLite and PostgreSQL.

-- One row per account once it has started a checkout. No row means the Free plan.
CREATE TABLE subscriptions (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  plan TEXT NOT NULL DEFAULT 'free',
  status TEXT NOT NULL DEFAULT 'none',
  provider TEXT NOT NULL DEFAULT '',
  provider_sub_id TEXT UNIQUE,
  current_end TEXT,
  cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
  last_event_at INTEGER NOT NULL DEFAULT 0,
  granted_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Payment-provider webhooks, kept once each so a retried delivery changes nothing.
CREATE TABLE billing_events (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  kind TEXT NOT NULL,
  provider_sub_id TEXT,
  received_at TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE INDEX billing_events_sub ON billing_events(provider_sub_id);

-- AI actions per account per calendar month: on the service's model (hosted) and on the user's own key (own).
CREATE TABLE ai_usage (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  period TEXT NOT NULL,
  hosted INTEGER NOT NULL DEFAULT 0,
  own INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, period)
);

-- A user's own model key, encrypted with SECRETS_KEY. Only the last four characters are ever shown.
CREATE TABLE ai_keys (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  base_url TEXT NOT NULL DEFAULT '',
  secret TEXT NOT NULL,
  hint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
