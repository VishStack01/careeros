"""Plans, billing and AI metering for Propelo Cloud.

Two plans:

  Free  everything that runs without a model (fresh matched roles, quoted checks, the pipeline,
        auto-apply from your own computer), daily matching, a small monthly allowance of AI
        actions on the service's model, and unlimited AI on your own key.
  Pro   hourly matching, a larger AI allowance on the service's model, a higher auto-apply cap
        and more file storage. Billed monthly through Razorpay subscriptions.

Payments: the server creates a Razorpay subscription and sends the person to Razorpay's hosted
page (`short_url`), so card and UPI details never touch this service. Razorpay then calls
`/api/billing/webhook`; every event is verified with the webhook secret and stored once by its
event id, so retries are harmless. The subscription's status decides the plan.

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

PLAN_IDS = ("free", "pro")
PRO_STATUSES = {"active", "pending"}  # pending: a renewal charge is being retried; Pro stays on meanwhile
OWN_PROVIDERS = ("anthropic", "openai", "gemini")
OPENAI_COMPATIBLE_HOSTS = {
    "api.openai.com", "openrouter.ai", "api.groq.com", "api.together.xyz", "api.deepseek.com",
    "api.mistral.ai", "api.x.ai", "api.fireworks.ai", "api.perplexity.ai",
}
RAZORPAY_API = "https://api.razorpay.com/v1"


class BillingError(RuntimeError):
    pass


# ---------------------------------------------------------------- catalog
def catalog(cfg: Config) -> list[dict]:
    return [
        {"id": "free", "name": "Free", "priceInr": 0, "aiCredits": cfg.free_ai_credits, "matchEveryHours": 24,
         "autoApplyPerDay": 5, "storageMb": min(cfg.user_storage_mb, 10),
         "features": ["Fresh roles from about 1,400 company career pages, matched daily",
                      "Every keep or skip with the quote that decided it",
                      "Pipeline, follow-ups, calendar and referral drafts",
                      f"{cfg.free_ai_credits} AI actions a month, unlimited with your own key",
                      "Auto-apply from your own computer, up to 5 a day"]},
        {"id": "pro", "name": "Pro", "priceInr": cfg.pro_price_inr, "aiCredits": cfg.pro_ai_credits, "matchEveryHours": 1,
         "autoApplyPerDay": 25, "storageMb": cfg.user_storage_mb,
         "features": ["Everything in Free",
                      "Matching every hour, so you see roles first",
                      f"{cfg.pro_ai_credits} AI actions a month on our model: tailored resumes, cover letters, fit scores",
                      "Auto-apply up to 25 a day",
                      "Priority support"]},
    ]


def plan_info(cfg: Config, plan: str) -> dict:
    return next(p for p in catalog(cfg) if p["id"] == plan)


def period(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


# ---------------------------------------------------------------- entitlement
def subscription(c: Conn, uid: str) -> dict | None:
    return c.one("SELECT * FROM subscriptions WHERE user_id = ?", (uid,))


def _future(ts: str | None) -> bool:
    return bool(ts) and ts > now_iso()


def plan_of(c: Conn, user: dict) -> str:
    if user.get("is_admin"):
        return "pro"
    s = subscription(c, user["id"])
    if not s or s["plan"] != "pro":
        return "free"
    if s["status"] == "granted":
        return "pro" if (not s["current_end"] or _future(s["current_end"])) else "free"
    if s["status"] in PRO_STATUSES:
        return "pro"
    if s["status"] == "cancelled" and _future(s["current_end"]):
        return "pro"  # paid until the end of the cycle
    return "free"


def usage(c: Conn, uid: str) -> dict:
    r = c.one("SELECT hosted, own FROM ai_usage WHERE user_id = ? AND period = ?", (uid, period()))
    return {"period": period(), "hosted": int(r["hosted"]) if r else 0, "own": int(r["own"]) if r else 0}


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


# ---------------------------------------------------------------- Razorpay
Post = Callable[[str, dict, str, str], dict]


def _post(url: str, body: dict, key_id: str, key_secret: str) -> dict:
    auth = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed https host
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            desc = json.loads(e.read().decode()).get("error", {}).get("description", "")
        except Exception:  # noqa: BLE001
            desc = ""
        raise BillingError(f"Razorpay said {e.code}{': ' + desc if desc else ''}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise BillingError(f"Couldn't reach Razorpay: {e}") from None


class Razorpay:
    def __init__(self, cfg: Config, post: Post | None = None):
        self.cfg, self.post = cfg, post or _post

    def create_subscription(self, uid: str, email: str) -> dict:
        # 120 monthly cycles is Razorpay's way of saying "until cancelled".
        body = {"plan_id": self.cfg.razorpay_plan_pro, "total_count": 120, "quantity": 1, "customer_notify": True,
                "notes": {"user_id": uid, "email": email[:120], "plan": "pro"}}
        sub = self.post(f"{RAZORPAY_API}/subscriptions", body, self.cfg.razorpay_key_id, self.cfg.razorpay_key_secret)
        if not str(sub.get("id", "")).startswith("sub_") or not str(sub.get("short_url", "")).startswith("https://"):
            raise BillingError("Razorpay returned an unexpected subscription.")
        return sub

    def cancel(self, sub_id: str, at_cycle_end: bool = True) -> dict:
        return self.post(f"{RAZORPAY_API}/subscriptions/{sub_id}/cancel", {"cancel_at_cycle_end": 1 if at_cycle_end else 0},
                         self.cfg.razorpay_key_id, self.cfg.razorpay_key_secret)


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not (secret and signature):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None
    except (TypeError, ValueError, OverflowError):
        return None


def start_checkout(c: Conn, uid: str, sub: dict) -> None:
    now = now_iso()
    existing = subscription(c, uid)
    if existing:
        c.execute("UPDATE subscriptions SET plan = 'pro', status = ?, provider = 'razorpay', provider_sub_id = ?, cancel_at_period_end = 0, "
                  "granted_by = NULL, updated_at = ? WHERE user_id = ?", (sub.get("status") or "created", sub["id"], now, uid))
    else:
        c.execute("INSERT INTO subscriptions(user_id, plan, status, provider, provider_sub_id, created_at, updated_at) "
                  "VALUES (?, 'pro', ?, 'razorpay', ?, ?, ?)", (uid, sub.get("status") or "created", sub["id"], now, now))


def apply_event(c: Conn, event_id: str, event: dict) -> str:
    """Record one verified webhook. Returns what happened: duplicate, ignored, unknown or the new status."""
    kind = str(event.get("event", ""))
    ent = (((event.get("payload") or {}).get("subscription") or {}).get("entity")) or {}
    sub_id = str(ent.get("id", ""))
    if c.one("SELECT 1 AS x FROM billing_events WHERE id = ?", (event_id,)):
        return "duplicate"
    c.execute("INSERT INTO billing_events(id, provider, kind, provider_sub_id, received_at, payload) VALUES (?, 'razorpay', ?, ?, ?, ?)",
              (event_id, kind, sub_id or None, now_iso(), json.dumps(event)[:20000]))
    if not kind.startswith("subscription.") or not sub_id:
        return "ignored"
    status = str(ent.get("status") or kind.split(".", 1)[1])
    end = _iso(ent.get("current_end")) or _iso(ent.get("end_at"))
    try:
        at = int(event.get("created_at") or 0)
    except (TypeError, ValueError):
        at = 0
    row = c.one("SELECT user_id, last_event_at FROM subscriptions WHERE provider_sub_id = ?", (sub_id,))
    if not row:
        # A payment on an older checkout link of the same account (the person opened checkout twice and paid the
        # first link). The payload is signed by Razorpay and carries the account id we put in its notes.
        uid = str(((ent.get("notes") or {}) if isinstance(ent.get("notes"), dict) else {}).get("user_id", ""))
        if not uid or status not in PRO_STATUSES or not c.one("SELECT 1 AS x FROM users WHERE id = ?", (uid,)):
            return "unknown"
        start_checkout(c, uid, {"id": sub_id, "status": status})
        row = {"user_id": uid, "last_event_at": 0}
    if at and int(row["last_event_at"] or 0) > at:
        return "stale"  # Razorpay doesn't promise order; a newer event already set the state
    c.execute("UPDATE subscriptions SET status = ?, current_end = COALESCE(?, current_end), last_event_at = ?, updated_at = ? "
              "WHERE provider_sub_id = ?", (status, end, max(at, int(row["last_event_at"] or 0)), now_iso(), sub_id))
    return status


def grant(c: Conn, uid: str, by: str, until: str | None) -> None:
    """An operator gives an account Pro without payment (beta testers, support). `until` is an ISO date or None."""
    now = now_iso()
    c.execute("DELETE FROM subscriptions WHERE user_id = ?", (uid,))
    c.execute("INSERT INTO subscriptions(user_id, plan, status, provider, current_end, granted_by, created_at, updated_at) "
              "VALUES (?, 'pro', 'granted', 'manual', ?, ?, ?, ?)", (uid, until, by, now, now))


def billing_view(c: Conn, cfg: Config, user: dict) -> dict:
    s = subscription(c, user["id"])
    plan = plan_of(c, user)
    return {
        "plan": plan, "plans": catalog(cfg), "checkoutEnabled": cfg.billing_enabled,
        "subscription": {"status": s["status"], "provider": s["provider"], "currentEnd": s["current_end"],
                         "cancelAtPeriodEnd": bool(s["cancel_at_period_end"]), "granted": s["status"] == "granted"} if s else None,
        "supportEmail": cfg.support_email,
    }
