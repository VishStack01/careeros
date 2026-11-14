"""Plans, billing and AI metering for Propelo Cloud.

Three plans:

  Free   everything that runs without a model (fresh matched roles, quoted checks, the pipeline,
         auto-apply from your own computer), daily matching, a small monthly allowance of AI
         actions on the service's model, and unlimited AI on your own key.
  Pro    hourly matching, a larger AI allowance, a higher auto-apply cap and more storage.
  Ultra  matching within 15 minutes of each scan, the largest AI allowance, the highest
         auto-apply cap, the copilot and mock interviews without limits, and LinkedIn review.

Payments: India pays in rupees through Razorpay subscriptions; everyone else pays in US dollars
through Dodo Payments, which is the merchant of record (it charges and files VAT and sales tax).
Either way the server creates the checkout and sends the person to the provider's hosted page,
so card and UPI details never touch this service. The provider then calls a webhook; every
event is verified (Razorpay: HMAC of the body; Dodo: Standard Webhooks), stored once by its id
so retries are harmless, and the subscription's status decides the plan.

Changing plan: the new checkout waits in `pending_*`. Only when the new subscription is paid does
it replace the old one, and the old one is cancelled then, so an abandoned checkout never takes
away a plan someone already pays for.

Own keys: a person may save their own Anthropic, OpenAI(-compatible) or Gemini key. It is
encrypted with SECRETS_KEY (Fernet: AES-128-CBC with HMAC-SHA256) and only its last four
characters are ever shown. OpenAI-compatible base URLs are limited to known public providers,
so the server can't be pointed at internal addresses.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from .. import llm
from .config import Config
from .db import Conn, now_iso

PLAN_IDS = ("free", "pro", "ultra")
PAID = ("pro", "ultra")
CURRENCIES = ("INR", "USD")
PRO_STATUSES = {"active", "pending"}  # pending: a renewal charge is being retried; the plan stays on meanwhile
OWN_PROVIDERS = ("anthropic", "openai", "gemini")
OPENAI_COMPATIBLE_HOSTS = {
    "api.openai.com", "openrouter.ai", "api.groq.com", "api.together.xyz", "api.deepseek.com",
    "api.mistral.ai", "api.x.ai", "api.fireworks.ai", "api.perplexity.ai",
}
RAZORPAY_API = "https://api.razorpay.com/v1"
DODO_API = {"live": "https://live.dodopayments.com", "test": "https://test.dodopayments.com"}


class BillingError(RuntimeError):
    pass


# ---------------------------------------------------------------- catalog
def usd(cents: int) -> str:
    return f"{cents / 100:.2f}"


def catalog(cfg: Config) -> list[dict]:
    return [
        {"id": "free", "name": "Free", "priceInr": 0, "priceUsd": "0", "aiCredits": cfg.free_ai_credits,
         "matchEveryMinutes": 24 * 60, "matchEveryHours": 24, "autoApplyPerDay": 5, "autoApplyPerMonth": 100, "storageMb": min(cfg.user_storage_mb, 10),
         "copilotPerDay": 10, "mockInterviews": 2, "autoEmailsPerDay": 0, "linkedinReview": False,
         "features": ["Fresh roles from company career pages, matched daily",
                      "Every keep or skip with the quote that decided it",
                      "Pipeline, contacts, follow-ups, calendar and referral drafts",
                      f"{cfg.free_ai_credits} AI actions a month, unlimited with your own key",
                      "Autofill extension, and auto-apply from your own computer up to 5 a day"]},
        {"id": "pro", "name": "Pro", "priceInr": cfg.pro_price_inr, "priceUsd": usd(cfg.pro_price_usd_cents), "aiCredits": cfg.pro_ai_credits,
         "matchEveryMinutes": 60, "matchEveryHours": 1, "autoApplyPerDay": 25, "autoApplyPerMonth": 500, "storageMb": cfg.user_storage_mb,
         "copilotPerDay": 60, "mockInterviews": 20, "autoEmailsPerDay": 10, "linkedinReview": False,
         "features": ["Everything in Free",
                      "Matching every hour, so you see roles first",
                      f"{cfg.pro_ai_credits} AI actions a month: tailored resumes, cover letters, fit scores",
                      "Auto-apply up to 500 a month (25 a day), with a receipt for each",
                      "Ask Propelo, the copilot, 60 questions a day, and 20 mock interviews a month",
                      "Recruiter emails sent from your Gmail, up to 10 a day, when you turn it on",
                      "Priority support"]},
        {"id": "ultra", "name": "Ultra", "priceInr": cfg.ultra_price_inr, "priceUsd": usd(cfg.ultra_price_usd_cents), "aiCredits": cfg.ultra_ai_credits,
         "matchEveryMinutes": 15, "matchEveryHours": 0.25, "autoApplyPerDay": 60, "autoApplyPerMonth": 1000, "storageMb": max(cfg.user_storage_mb, 100),
         "copilotPerDay": None, "mockInterviews": None, "autoEmailsPerDay": 25, "linkedinReview": True,
         "features": ["Everything in Pro",
                      "New roles matched within 15 minutes of each scan",
                      f"{cfg.ultra_ai_credits:,} AI actions a month",
                      "Auto-apply up to 1,000 a month (60 a day), every one above your apply line",
                      "Unlimited copilot questions and mock interviews",
                      "LinkedIn profile review",
                      "Recruiter emails from your Gmail, up to 25 a day, with day 7 and 14 follow-ups",
                      "Fastest support"]},
    ]


def plan_info(cfg: Config, plan: str) -> dict:
    return next(p for p in catalog(cfg) if p["id"] == plan)


def currency_for(country: str = "", tz: str = "") -> str:
    """Rupees for India, dollars everywhere else. The person can always switch on the pricing page."""
    return "INR" if (country or "").upper() == "IN" or tz in ("Asia/Kolkata", "Asia/Calcutta") else "USD"


def period(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


# ---------------------------------------------------------------- entitlement
def subscription(c: Conn, uid: str) -> dict | None:
    return c.one("SELECT * FROM subscriptions WHERE user_id = ?", (uid,))


def _future(ts: str | None) -> bool:
    return bool(ts) and ts > now_iso()


def _paid_plan(s: dict | None) -> str:
    """The plan a subscription row grants right now, or "free"."""
    if not s or s["plan"] not in PAID:
        return "free"
    if s["status"] == "granted":
        return s["plan"] if (not s["current_end"] or _future(s["current_end"])) else "free"
    if s["status"] in PRO_STATUSES:
        return s["plan"]
    if s["status"] == "cancelled" and _future(s["current_end"]):
        return s["plan"]  # paid until the end of the cycle
    return "free"


def plan_of(c: Conn, user: dict) -> str:
    if user.get("is_admin"):
        return "ultra"
    return _paid_plan(subscription(c, user["id"]))


def usage(c: Conn, uid: str) -> dict:
    r = c.one("SELECT hosted, own FROM ai_usage WHERE user_id = ? AND period = ?", (uid, period()))
    return {"period": period(), "hosted": int(r["hosted"]) if r else 0, "own": int(r["own"]) if r else 0}


FEATURES = {
    # feature: (catalog field with the allowance, "day" or "month", what it's called in messages)
    "copilot": ("copilotPerDay", "day", "copilot questions today"),
    "mock": ("mockInterviews", "month", "mock interviews this month"),
}


def feature_period(span: str, now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d" if span == "day" else "%Y-%m")


def take_feature(c: Conn, cfg: Config, uid: str, plan: str, feature: str) -> tuple[bool, str]:
    """Count one use of a metered feature. (allowed, message when not)."""
    if feature == "linkedin":
        return (True, "") if plan_info(cfg, plan)["linkedinReview"] else (False, "LinkedIn profile review is part of Ultra. Add your own AI key to use it on any plan.")
    if feature not in FEATURES:
        return True, ""
    field, span, noun = FEATURES[feature]
    limit = plan_info(cfg, plan)[field]
    if limit is None:
        return True, ""
    per = feature_period(span)
    c.execute("INSERT INTO feature_usage(user_id, period, feature, count) VALUES (?, ?, ?, 1) "
              "ON CONFLICT (user_id, period, feature) DO UPDATE SET count = feature_usage.count + 1", (uid, per, feature))
    n = int(c.scalar("SELECT count FROM feature_usage WHERE user_id = ? AND period = ? AND feature = ?", (uid, per, feature)) or 0)
    if n > limit:
        c.execute("UPDATE feature_usage SET count = count - 1 WHERE user_id = ? AND period = ? AND feature = ?", (uid, per, feature))
        nxt = "Ultra has no limit" if plan == "pro" else "Pro and Ultra allow more"
        return False, f"You've used your {limit} {noun}. {nxt}, or add your own AI key in Settings."
    return True, ""


def refund_feature(c: Conn, uid: str, feature: str) -> None:
    """Give back one use when the AI call behind it failed."""
    if feature in FEATURES:
        c.execute("UPDATE feature_usage SET count = count - 1 WHERE user_id = ? AND period = ? AND feature = ? AND count > 0",
                  (uid, feature_period(FEATURES[feature][1]), feature))


def feature_usage(c: Conn, cfg: Config, uid: str, plan: str) -> dict:
    out = {}
    for feature, (field, span, _) in FEATURES.items():
        r = c.one("SELECT count FROM feature_usage WHERE user_id = ? AND period = ? AND feature = ?", (uid, feature_period(span), feature))
        out[feature] = {"used": int(r["count"]) if r else 0, "limit": plan_info(cfg, plan)[field], "per": span}
    return out


def take_credit(c: Conn, uid: str, kind: str, limit: int | None = None) -> bool:
    """Count one AI action. For the service's model, refuse when the month's allowance is used up."""
    col = "hosted" if kind == "hosted" else "own"
    c.execute(f"INSERT INTO ai_usage(user_id, period, {col}) VALUES (?, ?, 1) "
              f"ON CONFLICT (user_id, period) DO UPDATE SET {col} = ai_usage.{col} + 1", (uid, period()))
    if limit is None:
        return True
    n = int(c.scalar(f"SELECT {col} FROM ai_usage WHERE user_id = ? AND period = ?", (uid, period())) or 0)
    if n > limit:
        c.execute(f"UPDATE ai_usage SET {col} = {col} - 1 WHERE user_id = ? AND period = ?", (uid, period()))
        return False
    return True


def refund_credit(c: Conn, uid: str, kind: str) -> None:
    col = "hosted" if kind == "hosted" else "own"
    c.execute(f"UPDATE ai_usage SET {col} = {col} - 1 WHERE user_id = ? AND period = ? AND {col} > 0", (uid, period()))


# ---------------------------------------------------------------- own keys
def _fernet(cfg: Config):
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:  # pragma: no cover - the cloud extra installs it
        raise BillingError("Saving your own key needs the 'cryptography' package on the server.") from e
    secret = cfg.secrets_key or ("dev-only:" + cfg.database_url if not cfg.is_production else "")
    if not secret:
        raise BillingError("SECRETS_KEY is not set.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def check_base_url(provider: str, base_url: str) -> str:
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        return ""
    if provider != "openai":
        raise ValueError("A custom address is only for OpenAI-compatible providers.")
    u = urlparse(base_url)
    if u.scheme != "https" or u.hostname not in OPENAI_COMPATIBLE_HOSTS or u.port not in (None, 443) or u.username or u.password:
        raise ValueError("Use the https address of a supported OpenAI-compatible provider: " + ", ".join(sorted(OPENAI_COMPATIBLE_HOSTS)) + ".")
    return base_url


def save_key(c: Conn, cfg: Config, uid: str, provider: str, key: str, model: str = "", base_url: str = "") -> dict:
    provider = (provider or "").strip().lower()
    key = (key or "").strip()
    if provider not in OWN_PROVIDERS:
        raise ValueError("Choose Anthropic, OpenAI (or an OpenAI-compatible provider) or Gemini.")
    if not (16 <= len(key) <= 400) or any(ch.isspace() for ch in key):
        raise ValueError("That doesn't look like an API key.")
    model = (model or "").strip()[:80]
    base_url = check_base_url(provider, base_url)
    token = _fernet(cfg).encrypt(key.encode()).decode()
    now = now_iso()
    c.execute("DELETE FROM ai_keys WHERE user_id = ?", (uid,))
    c.execute("INSERT INTO ai_keys(user_id, provider, model, base_url, secret, hint, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (uid, provider, model, base_url, token, key[-4:], now, now))
    return public_key(c, uid)


def public_key(c: Conn, uid: str) -> dict | None:
    r = c.one("SELECT provider, model, base_url, hint, updated_at FROM ai_keys WHERE user_id = ?", (uid,))
    return {"provider": r["provider"], "model": r["model"], "baseUrl": r["base_url"], "hint": "…" + r["hint"], "updatedAt": r["updated_at"]} if r else None


def delete_key(c: Conn, uid: str) -> None:
    c.execute("DELETE FROM ai_keys WHERE user_id = ?", (uid,))


def own_config(c: Conn, cfg: Config, uid: str) -> llm.Config | None:
    r = c.one("SELECT provider, model, base_url, secret FROM ai_keys WHERE user_id = ?", (uid,))
    if not r:
        return None
    key = _fernet(cfg).decrypt(r["secret"].encode()).decode()
    env = {"CAREEROS_LLM": r["provider"], llm.KEY_VARS[r["provider"]]: key}
    if r["model"]:
        env["CAREEROS_MODEL"] = r["model"]
    if r["base_url"]:
        env["OPENAI_BASE_URL"] = r["base_url"]
    return llm.config(env)


def hosted_config(env: dict | None = None) -> llm.Config | None:
    """The service's own model, from the server's environment (CAREEROS_LLM and a provider key). Never Ollama."""
    env = os.environ if env is None else env
    try:
        cfg = llm.config(env)
    except llm.LLMError:
        return None
    return cfg if cfg and cfg.provider != "ollama" else None


def hosted_fallback(env: dict | None = None) -> llm.Config | None:
    """A second provider for the service's model (CAREEROS_LLM_FALLBACK plus that provider's key), used
    once when the first fails, so one provider's outage doesn't stop everyone's AI actions."""
    env = dict(os.environ if env is None else env)
    name = (env.get("CAREEROS_LLM_FALLBACK") or "").strip().lower()
    if not name or name == "ollama":
        return None
    env["CAREEROS_LLM"] = name
    for k in ("CAREEROS_MODEL", "CAREEROS_MODEL_QUICK"):
        env.pop(k, None)
    if env.get("CAREEROS_FALLBACK_MODEL"):
        env["CAREEROS_MODEL"] = env["CAREEROS_FALLBACK_MODEL"]
    try:
        return llm.config(env)
    except llm.LLMError:
        return None


def ai_status(c: Conn, cfg: Config, user: dict, env: dict | None = None) -> dict:
    plan = plan_of(c, user)
    limit = plan_info(cfg, plan)["aiCredits"]
    u = usage(c, user["id"])
    own = public_key(c, user["id"])
    hosted = hosted_config(env) is not None
    source = "own" if own else "hosted" if hosted else "none"
    left = max(0, limit - u["hosted"]) if hosted else 0
    return {"source": source, "available": bool(own) or (hosted and left > 0), "hostedAvailable": hosted,
            "limit": limit, "used": u["hosted"], "left": left, "ownUsed": u["own"], "period": u["period"], "ownKey": own}


# ---------------------------------------------------------------- providers
Post = Callable[..., dict]


def _request(method: str, url: str, body: dict | None, headers: dict, who: str) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed https hosts
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            raw = json.loads(e.read().decode())
            desc = (raw.get("error") or {}).get("description", "") if isinstance(raw.get("error"), dict) else str(raw.get("message") or raw.get("error") or "")
        except Exception:  # noqa: BLE001
            desc = ""
        raise BillingError(f"{who} said {e.code}{': ' + desc[:200] if desc else ''}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise BillingError(f"Couldn't reach {who}: {e}") from None


def _post(url: str, body: dict, key_id: str, key_secret: str) -> dict:
    auth = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    return _request("POST", url, body, {"Authorization": f"Basic {auth}"}, "Razorpay")


class Razorpay:
    name = "razorpay"

    def __init__(self, cfg: Config, post: Post | None = None):
        self.cfg, self.post = cfg, post or _post

    def plan_id(self, plan: str) -> str:
        return {"pro": self.cfg.razorpay_plan_pro, "ultra": self.cfg.razorpay_plan_ultra}.get(plan, "")

    def offers(self, plan: str) -> bool:
        return self.cfg.razorpay_enabled and bool(self.plan_id(plan))

    def create_subscription(self, uid: str, email: str, plan: str = "pro") -> dict:
        # 120 monthly cycles is Razorpay's way of saying "until cancelled".
        body = {"plan_id": self.plan_id(plan), "total_count": 120, "quantity": 1, "customer_notify": True,
                "notes": {"user_id": uid, "email": email[:120], "plan": plan}}
        sub = self.post(f"{RAZORPAY_API}/subscriptions", body, self.cfg.razorpay_key_id, self.cfg.razorpay_key_secret)
        if not str(sub.get("id", "")).startswith("sub_") or not str(sub.get("short_url", "")).startswith("https://"):
            raise BillingError("Razorpay returned an unexpected subscription.")
        return {"id": sub["id"], "url": sub["short_url"], "status": sub.get("status") or "created"}

    def cancel(self, sub_id: str, at_cycle_end: bool = True) -> dict:
        return self.post(f"{RAZORPAY_API}/subscriptions/{sub_id}/cancel", {"cancel_at_cycle_end": 1 if at_cycle_end else 0},
                         self.cfg.razorpay_key_id, self.cfg.razorpay_key_secret)


def _dodo_request(method: str, url: str, body: dict | None, key: str) -> dict:
    return _request(method, url, body, {"Authorization": f"Bearer {key}"}, "Dodo Payments")


class Dodo:
    """Dodo Payments, for payments in US dollars. Hosted checkout sessions; Standard Webhooks."""
    name = "dodo"

    def __init__(self, cfg: Config, call: Callable[..., dict] | None = None):
        self.cfg, self.call = cfg, call or _dodo_request
        self.base = DODO_API["live" if cfg.dodo_live else "test"]

    def product(self, plan: str) -> str:
        return {"pro": self.cfg.dodo_product_pro, "ultra": self.cfg.dodo_product_ultra}.get(plan, "")

    def offers(self, plan: str) -> bool:
        return self.cfg.dodo_enabled and bool(self.product(plan))

    def create_subscription(self, uid: str, email: str, plan: str = "pro", name: str = "") -> dict:
        body = {"product_cart": [{"product_id": self.product(plan), "quantity": 1}],
                "customer": {"email": email[:200], "name": (name or email.split("@")[0])[:120]},
                "return_url": f"{self.cfg.public_url}/app#settings", "metadata": {"user_id": uid, "plan": plan}}
        r = self.call("POST", f"{self.base}/checkouts", body, self.cfg.dodo_api_key)
        url, sid = str(r.get("checkout_url") or ""), str(r.get("session_id") or "")
        if not url.startswith("https://") or not sid:
            raise BillingError("Dodo Payments returned an unexpected checkout.")
        return {"id": sid, "url": url, "status": "created"}

    def cancel(self, sub_id: str, at_cycle_end: bool = True) -> dict:
        body = {"cancel_at_next_billing_date": True} if at_cycle_end else {"status": "cancelled"}
        return self.call("PATCH", f"{self.base}/subscriptions/{sub_id}", body, self.cfg.dodo_api_key)

    def portal(self, customer_id: str) -> str:
        r = self.call("POST", f"{self.base}/customers/{customer_id}/customer-portal/session", {}, self.cfg.dodo_api_key)
        link = str(r.get("link") or r.get("url") or "")
        if not link.startswith("https://"):
            raise BillingError("Dodo Payments returned no portal link.")
        return link


# ---------------------------------------------------------------- webhook signatures
def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Razorpay: hex HMAC-SHA256 of the raw body with the webhook secret."""
    if not (secret and signature):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def verify_standard_webhook(body: bytes, headers: dict, secret: str, now: float | None = None, tolerance: int = 300) -> bool:
    """Standard Webhooks (Dodo): base64 HMAC-SHA256 of "{id}.{timestamp}.{body}" with the base64-decoded
    whsec_ secret; any of the space-separated "v1,<sig>" values may match; the timestamp must be fresh."""
    wid, ts, sigs = headers.get("webhook-id", ""), headers.get("webhook-timestamp", ""), headers.get("webhook-signature", "")
    if not (secret and wid and ts and sigs):
        return False
    try:
        if abs((now if now is not None else datetime.now(timezone.utc).timestamp()) - int(ts)) > tolerance:
            return False
        key = base64.b64decode(secret[6:] if secret.startswith("whsec_") else secret)
    except (ValueError, TypeError):
        return False
    expected = base64.b64encode(hmac.new(key, f"{wid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, part.split(",", 1)[1]) for part in sigs.split() if part.startswith("v1,") and "," in part)


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None
    except (TypeError, ValueError, OverflowError):
        return None


def _iso_text(ts) -> str | None:
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- checkout and events
def start_checkout(c: Conn, uid: str, sub: dict, plan: str = "pro", provider: str = "razorpay", currency: str = "INR") -> None:
    """Remember a new checkout. Someone already on a paid plan keeps it: the checkout waits as pending."""
    now = now_iso()
    existing = subscription(c, uid)
    if existing and _paid_plan(existing) != "free" and existing["status"] != "granted":
        c.execute("UPDATE subscriptions SET pending_plan = ?, pending_provider = ?, pending_sub_id = ?, updated_at = ? WHERE user_id = ?",
                  (plan, provider, sub["id"], now, uid))
    elif existing:
        c.execute("UPDATE subscriptions SET plan = ?, status = ?, provider = ?, provider_sub_id = ?, currency = ?, cancel_at_period_end = 0, "
                  "granted_by = NULL, pending_plan = NULL, pending_provider = NULL, pending_sub_id = NULL, last_event_at = 0, updated_at = ? "
                  "WHERE user_id = ?", (plan, sub.get("status") or "created", provider, sub["id"], currency, now, uid))
    else:
        c.execute("INSERT INTO subscriptions(user_id, plan, status, provider, provider_sub_id, currency, created_at, updated_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (uid, plan, sub.get("status") or "created", provider, sub["id"], currency, now, now))


def _plan_by_id(ids: dict, value) -> str:
    """Which plan a provider's plan or product id is. Unset ids never match."""
    return ids.get(str(value), "") if value and str(value) in {k for k in ids if k} else ""


def razorpay_event(cfg: Config, event: dict) -> dict:
    """Normalise a Razorpay webhook into the fields `apply` needs."""
    ent = (((event.get("payload") or {}).get("subscription") or {}).get("entity")) or {}
    notes = ent.get("notes") if isinstance(ent.get("notes"), dict) else {}
    plan = _plan_by_id({cfg.razorpay_plan_pro: "pro", cfg.razorpay_plan_ultra: "ultra"}, ent.get("plan_id")) or str(notes.get("plan", ""))
    kind = str(event.get("event", ""))
    try:
        at = int(event.get("created_at") or 0)
    except (TypeError, ValueError):
        at = 0
    return {"provider": "razorpay", "kind": kind, "sub_id": str(ent.get("id", "")),
            "status": str(ent.get("status") or (kind.split(".", 1)[1] if "." in kind else "")),
            "end": _iso(ent.get("current_end")) or _iso(ent.get("end_at")), "at": at,
            "uid": str(notes.get("user_id", "")), "plan": plan if plan in PAID else "", "customer": str(ent.get("customer_id") or ""),
            "currency": "INR", "scheduled_cancel": False}


DODO_STATUS = {"active": "active", "renewed": "active", "updated": "", "plan_changed": "", "on_hold": "pending", "past_due": "pending",
               "failed": "halted", "cancelled": "cancelled", "expired": "expired", "paused": "halted", "unpaused": "active"}


def dodo_event(cfg: Config, event: dict) -> dict:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    kind = str(event.get("type", ""))
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    cust = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    plan = _plan_by_id({cfg.dodo_product_pro: "pro", cfg.dodo_product_ultra: "ultra"}, data.get("product_id")) or str(meta.get("plan", ""))
    raw = str(data.get("status") or "").lower()
    status = DODO_STATUS.get(kind.split(".", 1)[1] if "." in kind else "", "") or DODO_STATUS.get(raw, raw)
    ts = _iso_text(event.get("timestamp"))
    at = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()) if ts else 0
    return {"provider": "dodo", "kind": kind, "sub_id": str(data.get("subscription_id", "")), "status": status,
            "end": _iso_text(data.get("next_billing_date")) or _iso_text(data.get("expires_at")), "at": at,
            "uid": str(meta.get("user_id", "")), "plan": plan if plan in PAID else "", "customer": str(cust.get("customer_id") or ""),
            "email": str(cust.get("email") or ""), "currency": "USD", "scheduled_cancel": bool(data.get("cancel_at_next_billing_date"))}


def apply(c: Conn, event_id: str, ev: dict, payload: dict) -> tuple[str, dict | None]:
    """Record one verified, normalised webhook. Returns (what happened, a superseded subscription to cancel or None)."""
    provider, sub_id, status, kind = ev["provider"], ev["sub_id"], ev["status"], ev["kind"]
    if c.one("SELECT 1 AS x FROM billing_events WHERE id = ?", (event_id,)):
        return "duplicate", None
    c.execute("INSERT INTO billing_events(id, provider, kind, provider_sub_id, received_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
              (event_id, provider, kind, sub_id or None, now_iso(), json.dumps(payload)[:20000]))
    if not kind.startswith("subscription.") or not sub_id or not status:
        return "ignored", None
    now = now_iso()
    row = c.one("SELECT * FROM subscriptions WHERE provider_sub_id = ?", (sub_id,))
    if not row and ev["uid"]:
        # A checkout this account started: either a waiting plan change, or (Dodo) the first subscription,
        # whose id we only learn now. The payload is signed and carries the account id we put in its metadata.
        cand = c.one("SELECT * FROM subscriptions WHERE user_id = ?", (ev["uid"],))
        if cand and (cand["pending_provider"] == provider or (cand["provider"] == provider and _paid_plan(cand) == "free")):
            row = cand
        elif not cand and status in PRO_STATUSES and c.one("SELECT 1 AS x FROM users WHERE id = ?", (ev["uid"],)):
            start_checkout(c, ev["uid"], {"id": sub_id, "status": status}, ev["plan"] or "pro", provider, ev["currency"])
            row = subscription(c, ev["uid"])
    if not row:
        return "unknown", None
    if row["provider_sub_id"] != sub_id:
        is_pending = row["pending_provider"] == provider
        if status not in PRO_STATUSES:
            return ("pending-" + status if is_pending else "unknown"), None
        old = {"provider": row["provider"], "sub_id": row["provider_sub_id"]} if is_pending and _paid_plan(row) != "free" and row["status"] != "granted" else None
        plan = ev["plan"] or (row["pending_plan"] if is_pending else row["plan"]) or "pro"
        c.execute("UPDATE subscriptions SET plan = ?, status = ?, provider = ?, provider_sub_id = ?, currency = ?, current_end = ?, "
                  "provider_customer_id = COALESCE(?, provider_customer_id), cancel_at_period_end = 0, granted_by = NULL, "
                  "pending_plan = NULL, pending_provider = NULL, pending_sub_id = NULL, last_event_at = ?, updated_at = ? WHERE user_id = ?",
                  (plan, status, provider, sub_id, ev["currency"], ev["end"], ev["customer"] or None, ev["at"], now, row["user_id"]))
        return status, old
    if ev["at"] and int(row["last_event_at"] or 0) > ev["at"]:
        return "stale", None  # providers don't promise order; a newer event already set the state
    c.execute("UPDATE subscriptions SET status = ?, plan = COALESCE(?, plan), current_end = COALESCE(?, current_end), "
              "provider_customer_id = COALESCE(?, provider_customer_id), cancel_at_period_end = CASE WHEN ? = 1 THEN 1 ELSE cancel_at_period_end END, "
              "last_event_at = ?, updated_at = ? WHERE provider_sub_id = ?",
              (status, ev["plan"] or None, ev["end"], ev["customer"] or None, 1 if ev["scheduled_cancel"] else 0,
               max(ev["at"], int(row["last_event_at"] or 0)), now, sub_id))
    return status, None


def apply_event(c: Conn, event_id: str, event: dict, cfg: Config | None = None) -> str:
    """Razorpay webhook, kept for callers of the 1.x API."""
    ev = razorpay_event(cfg or Config(), event)
    return apply(c, event_id, ev, event)[0]


def grant(c: Conn, uid: str, by: str, until: str | None, plan: str = "pro") -> None:
    """An operator gives an account a paid plan without payment (beta testers, support). `until` is an ISO date or None."""
    plan = plan if plan in PAID else "pro"
    now = now_iso()
    c.execute("DELETE FROM subscriptions WHERE user_id = ?", (uid,))
    c.execute("INSERT INTO subscriptions(user_id, plan, status, provider, current_end, granted_by, created_at, updated_at) "
              "VALUES (?, ?, 'granted', 'manual', ?, ?, ?, ?)", (uid, plan, until, by, now, now))


def billing_view(c: Conn, cfg: Config, user: dict) -> dict:
    s = subscription(c, user["id"])
    plan = plan_of(c, user)
    return {
        "plan": plan, "plans": catalog(cfg), "checkoutEnabled": cfg.billing_enabled,
        "currencies": [x for x, on in (("INR", cfg.razorpay_enabled), ("USD", cfg.dodo_enabled)) if on],
        "subscription": {"plan": s["plan"], "status": s["status"], "provider": s["provider"], "currency": s["currency"], "currentEnd": s["current_end"],
                         "cancelAtPeriodEnd": bool(s["cancel_at_period_end"]), "granted": s["status"] == "granted",
                         "pendingPlan": s["pending_plan"], "portal": bool(s["provider"] == "dodo" and s["provider_customer_id"])} if s else None,
        "supportEmail": cfg.support_email,
    }
