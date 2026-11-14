-- Recruiter emails sent from the person's own Gmail, when they turn automatic sending on.

-- One connected mailbox per account. The refresh token is encrypted with SECRETS_KEY.
CREATE TABLE mailboxes (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  address TEXT NOT NULL,
  secret TEXT NOT NULL,
  connected_at TEXT NOT NULL,
  last_error TEXT,
  updated_at TEXT NOT NULL
);

-- Every automatic email, once per role and kind (first, follow1, follow2), so nothing is sent twice.
CREATE TABLE outreach_sends (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  to_addr TEXT NOT NULL,
  to_source TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL,
  thread_id TEXT,
  message_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  UNIQUE (user_id, job_id, kind)
);
CREATE INDEX outreach_sends_user ON outreach_sends(user_id, created_at);
CREATE INDEX outreach_sends_to ON outreach_sends(user_id, to_addr);

-- Addresses that asked not to be emailed, honoured for every Propelo user. Only a hash is kept.
CREATE TABLE email_optouts (
  address_hash TEXT PRIMARY KEY,
  at TEXT NOT NULL
);
