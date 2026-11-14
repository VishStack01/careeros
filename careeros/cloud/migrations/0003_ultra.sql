-- Ultra, international billing and plan changes.
-- currency: INR (Razorpay) or USD (Dodo Payments). A plan change waits in pending_* until the new
-- subscription is paid, so an abandoned checkout never takes away the plan someone already has.
ALTER TABLE subscriptions ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR';
ALTER TABLE subscriptions ADD COLUMN provider_customer_id TEXT;
ALTER TABLE subscriptions ADD COLUMN pending_plan TEXT;
ALTER TABLE subscriptions ADD COLUMN pending_provider TEXT;
ALTER TABLE subscriptions ADD COLUMN pending_sub_id TEXT;
CREATE INDEX subscriptions_pending ON subscriptions(pending_sub_id);
