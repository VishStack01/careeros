-- CareerOS Cloud: initial schema. Portable SQL for SQLite and PostgreSQL.
-- Ids are TEXT, timestamps are ISO-8601 UTC TEXT, JSON is TEXT, booleans are INTEGER 0/1.

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  email_verified_at TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0,
  disabled_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_login_at TEXT,
  password_changed_at TEXT
);

-- Browser sessions. Only a SHA-256 of the token is stored.
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  ip TEXT NOT NULL DEFAULT '',
  user_agent TEXT NOT NULL DEFAULT '',
  revoked_at TEXT
);
CREATE INDEX sessions_user ON sessions(user_id);

-- Computer keys: long-lived tokens for the user's own apply agent, scope "agent".
CREATE TABLE api_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  scopes TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  expires_at TEXT,
  revoked_at TEXT
);
CREATE INDEX api_tokens_user ON api_tokens(user_id);

-- Email verification and password reset links. Single use, short-lived, hashed.
CREATE TABLE one_time_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT
);
CREATE INDEX one_time_tokens_user ON one_time_tokens(user_id, purpose);

CREATE TABLE rate_limits (
  key TEXT NOT NULL,
  window_start TEXT NOT NULL,
  count INTEGER NOT NULL,
  PRIMARY KEY (key, window_start)
);

-- Each user's documents, in the dashboard's document model (jobs, runs, settings, brain, profile).
CREATE TABLE docs (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  collection TEXT NOT NULL,
  id TEXT NOT NULL,
  data TEXT NOT NULL,
  version INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, collection, id)
);
CREATE INDEX docs_user_updated ON docs(user_id, collection, updated_at);

-- Uploaded files (resumes). Bytes live in the storage backend under storage_key.
CREATE TABLE assets (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  text TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX assets_user ON assets(user_id);

-- Submission state machine: one row per user + destination. "submitted" is final.
CREATE TABLE applications (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  job_id TEXT NOT NULL,
  company_key TEXT NOT NULL,
  state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  receipt TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, key)
);
CREATE INDEX applications_company ON applications(user_id, company_key, state);

-- The shared job inventory, read from the hourly scan. Not tied to any user.
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  source TEXT NOT NULL,
  posted_at TEXT NOT NULL DEFAULT '',
  record TEXT NOT NULL,
  text TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE INDEX jobs_active ON jobs(active, first_seen_at);

CREATE TABLE feed_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Per-user matching bookkeeping.
CREATE TABLE match_state (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  settings_hash TEXT NOT NULL DEFAULT '',
  last_match_at TEXT,
  last_feed_at TEXT
);

-- Durable task queue with leases, retries and dedupe.
CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  payload TEXT NOT NULL DEFAULT '{}',
  dedupe_key TEXT,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  run_after TEXT NOT NULL,
  locked_by TEXT,
  locked_until TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE UNIQUE INDEX tasks_dedupe ON tasks(dedupe_key) WHERE status IN ('queued', 'running');
CREATE INDEX tasks_due ON tasks(status, run_after);

-- Security-relevant account events (sign-ins, password changes, keys, exports).
CREATE TABLE audit_events (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  at TEXT NOT NULL,
  kind TEXT NOT NULL,
  ip TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX audit_events_user ON audit_events(user_id, at);
