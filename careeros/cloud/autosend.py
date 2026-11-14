"""Automatic recruiter emails, sent from the person's own Gmail when they turn it on.

What must all be true before anything is sent:
  - the person connected Gmail, switched automatic sending on and approved the template
    (approving again whenever they change it);
  - their plan allows it (Pro 10 a day, Ultra 25 a day; Free drafts only);
  - the role was applied to in the last 3 days and isn't marked unsafe by the scam check;
  - the recipient's address was found on a public page, and that page is recorded. Guessed
    addresses (firstname@company.com) are never used: they bounce and get the mailbox flagged;
  - the address isn't a free personal mailbox, hasn't opted out of Propelo emails, and hasn't
    had a first email from this person in the last 30 days;
  - it's a weekday between 09:00 and 18:00 in the person's time zone.

Follow-ups go on day 7 and day 14 in the same thread, only if the person turned them on and
nothing has moved: the role is still "applied", the Inbox has nothing from that address, and
the person hasn't pressed Stop. Every email carries a line and a one-click header to opt out,
and every send is written to the role's timeline. A send that may have gone out is never retried.
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import mailbox, plans, repo
from .config import Config
from .db import Conn, Database, now_iso

FREE_MAIL = re.compile(r"@(gmail|googlemail|yahoo|ymail|outlook|hotmail|live|rediffmail|proton|protonmail|icloud|aol|zoho)\.", re.I)
EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\Z")
FIRST_WINDOW = timedelta(days=3)
FIRST_DELAY = timedelta(hours=2)
SAME_PERSON = timedelta(days=30)
FOLLOW = {"follow1": ("first", 7), "follow2": ("follow1", 14)}

DEFAULT_TEMPLATE = {
    "subject": "My application for {role} at {company}",
    "body": ("Hi {first_name},\n\nI applied for the {role} role at {company} and wanted to say hello directly. "
             "{highlight}\n\nIf it's useful, I'd be glad to talk for 15 minutes. My profile: {my_link}\n\nThanks,\n{my_name}"),
    "followUp": ("Hi {first_name},\n\nA short follow-up on my application for {role}. I'm still keen, and happy to share "
                 "anything that helps.\n\nThanks,\n{my_name}"),
}


# ---------------------------------------------------------------- opt-out links
def _key(cfg: Config) -> bytes:
    return hashlib.sha256(("propelo-optout|" + cfg.secrets_key).encode()).digest()


def address_hash(addr: str) -> str:
    return hashlib.sha256(addr.strip().lower().encode()).hexdigest()


def optout_token(cfg: Config, addr: str) -> tuple[str, str]:
    a = base64.urlsafe_b64encode(addr.strip().lower().encode()).decode().rstrip("=")
    s = hmac.new(_key(cfg), addr.strip().lower().encode(), hashlib.sha256).hexdigest()[:32]
    return a, s


def optout_url(cfg: Config, addr: str) -> str:
    a, s = optout_token(cfg, addr)
    return f"{cfg.public_url}/optout?a={a}&s={s}"


def read_optout(cfg: Config, a: str, s: str) -> str | None:
    try:
        addr = base64.urlsafe_b64decode(a + "=" * (-len(a) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    good = hmac.new(_key(cfg), addr.encode(), hashlib.sha256).hexdigest()[:32]
    return addr if EMAIL.match(addr) and hmac.compare_digest(good, s or "") else None


def opt_out(c: Conn, addr: str) -> None:
    c.execute("INSERT INTO email_optouts(address_hash, at) VALUES (?, ?) ON CONFLICT (address_hash) DO NOTHING", (address_hash(addr), now_iso()))
    c.execute("UPDATE outreach_sends SET status = 'cancelled', error = 'The recipient opted out.' WHERE to_addr = ? AND status = 'queued'", (addr.lower(),))


def opted_out(c: Conn, addr: str) -> bool:
    return bool(c.one("SELECT 1 AS x FROM email_optouts WHERE address_hash = ?", (address_hash(addr),)))


# ---------------------------------------------------------------- mailbox storage
def save_mailbox(c: Conn, cfg: Config, uid: str, address: str, refresh_token: str) -> None:
    secret = plans._fernet(cfg).encrypt(refresh_token.encode()).decode()
    now = now_iso()
    c.execute("INSERT INTO mailboxes(user_id, provider, address, secret, connected_at, updated_at) VALUES (?, 'gmail', ?, ?, ?, ?) "
              "ON CONFLICT (user_id) DO UPDATE SET address = excluded.address, secret = excluded.secret, connected_at = excluded.connected_at, "
              "last_error = NULL, updated_at = excluded.updated_at", (uid, address, secret, now, now))


def mailbox_row(c: Conn, uid: str) -> dict | None:
    return c.one("SELECT user_id, provider, address, secret, connected_at, last_error FROM mailboxes WHERE user_id = ?", (uid,))


def refresh_token(cfg: Config, row: dict) -> str:
    return plans._fernet(cfg).decrypt(row["secret"].encode()).decode()


# ---------------------------------------------------------------- settings and text
def settings(c: Conn, uid: str) -> dict:
    d = (repo.get_doc(c, uid, "settings", "outreach") or {"data": {}})["data"]
    t = d.get("template") if isinstance(d.get("template"), dict) else {}
    return {"on": d.get("autoSend") is True, "followUps": d.get("followUps") is True, "approvedAt": str(d.get("approvedAt") or ""),
            "timezone": str(d.get("timezone") or "")[:64],
            "subject": str(t.get("subject") or DEFAULT_TEMPLATE["subject"])[:200],
            "body": str(t.get("body") or DEFAULT_TEMPLATE["body"])[:4000],
            "followUp": str(t.get("followUp") or DEFAULT_TEMPLATE["followUp"])[:3000]}


def template_hash(s: dict) -> str:
    return hashlib.sha256(json.dumps([s["subject"], s["body"], s["followUp"]]).encode()).hexdigest()[:16]


def fill(text: str, values: dict) -> str:
    out = re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), text)
    # An empty value (no highlight, say) mustn't leave stray spaces or blank-line runs behind.
    out = "\n".join(line.rstrip() for line in out.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def footer(cfg: Config, name: str, to: str) -> str:
    return (f"\n\n--\nSent by {name or 'the candidate'} with Propelo. If you'd rather not get emails from Propelo users, "
            f"reply \"stop\" or use this link: {optout_url(cfg, to)}")


def _recipient(d: dict) -> tuple[str, str, str]:
    """(address, public source URL, first name) from the role's outreach, or blanks."""
    o = d.get("outreach") if isinstance(d.get("outreach"), dict) else {}
    em = o.get("email") if isinstance(o.get("email"), dict) else {}
    co = o.get("contact") if isinstance(o.get("contact"), dict) else {}
    addr = str(em.get("to") or co.get("email") or "").strip().lower()
    src = str(em.get("source") or co.get("emailSource") or co.get("source") or "").strip()
    first = re.sub(r"\(.*?\)", "", str(co.get("name") or "")).strip().split(" ")[0] if co.get("name") else ""
    return addr, src, first


def why_not(d: dict, addr: str, src: str) -> str:
    """The reason a role can't get an automatic email, or ""."""
    if not addr:
        return "No recruiter address found yet."
    if not EMAIL.match(addr):
        return "The recruiter address isn't valid."
    if not re.match(r"^https://", src):
        return "The address has no public source, so it isn't used."
    if FREE_MAIL.search(addr):
        return "The address is a personal mailbox, not the company's."
    if (d.get("risk") or {}).get("level") == "high":
        return "The posting looks unsafe."
    return ""


# ---------------------------------------------------------------- planning
def _ts(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _business_hours(now: datetime, tz: str) -> bool:
    try:
        local = now.astimezone(ZoneInfo(tz or "Asia/Kolkata"))
    except Exception:  # noqa: BLE001
        local = now.astimezone(ZoneInfo("Asia/Kolkata"))
    return local.weekday() < 5 and 9 <= local.hour < 18


def plan_user(c: Conn, cfg: Config, user: dict, now: datetime | None = None) -> list[dict]:
    """Queue the emails that are due for one account. Returns the queued rows."""
    now = now or datetime.now(timezone.utc)
    uid = user["id"]
    s = settings(c, uid)
    box = mailbox_row(c, uid)
    plan = plans.plan_of(c, user)
    cap = plans.plan_info(cfg, plan)["autoEmailsPerDay"]
    if not (s["on"] and box and cap and s["approvedAt"] == template_hash(s)):
        return []
    # The time zone the browser reported when sending was set up, else the search settings', else India.
    prof = repo.get_doc(c, uid, "settings", "profile")
    tz = s["timezone"] or str(((prof or {}).get("data") or {}).get("timezone") or "Asia/Kolkata")
    if not _business_hours(now, tz):
        return []
    day = now_iso(timedelta(hours=-24))
    room = cap - int(c.scalar("SELECT COUNT(*) AS n FROM outreach_sends WHERE user_id = ? AND status IN ('sent', 'sending', 'queued') AND created_at > ?", (uid, day)) or 0)
    if room <= 0:
        return []
    applicant = ((repo.get_doc(c, uid, "profile", "applicant") or {}).get("data") or {})
    me = {"my_name": str(applicant.get("fullName") or user.get("name") or "").strip(),
          "my_link": str(applicant.get("linkedin") or applicant.get("portfolio") or applicant.get("github") or "").strip()}
    inbox_from = {str((d["data"] or {}).get("from") or "").lower() for d in repo.list_docs(c, uid, "inbox")}
    sent = {(r["job_id"], r["kind"]): r for r in c.all("SELECT * FROM outreach_sends WHERE user_id = ?", (uid,))}
    recent_to = {r["to_addr"] for r in sent.values() if r["kind"] == "first" and r["status"] == "sent" and (_ts(r["sent_at"]) or now) > now - SAME_PERSON}
    queued = []
    for doc in repo.list_docs(c, uid, "jobs"):
        if room <= 0:
            break
        jid, d = doc["id"], doc["data"]
        addr, src, first = _recipient(d)
        if why_not(d, addr, src) or opted_out(c, addr):
            continue
        o = d.get("outreach") if isinstance(d.get("outreach"), dict) else {}
        em0 = o.get("email") if isinstance(o.get("email"), dict) else {}
        if o.get("stopped") or (em0.get("status") in ("sent", "replied", "stopped") and (jid, "first") not in sent):
            continue  # the person stopped it, or sent this one themselves
        ev0 = d.get("evidence")[0] if isinstance(d.get("evidence"), list) and d.get("evidence") else {}
        hl = str(ev0.get("evidence") or "").strip() if isinstance(ev0, dict) else ""
        values = dict(me, first_name=first or "there", role=str(d.get("title") or "the role"), company=str(d.get("company") or "your team"),
                      highlight=f"One thing relevant to the role: {hl.rstrip('.')}." if hl else "")
        applied = _ts(d.get("appliedAt"))
        if (jid, "first") not in sent:
            if d.get("stage") != "applied" or not applied or not (now - FIRST_WINDOW <= applied <= now - FIRST_DELAY) or addr in recent_to:
                continue
            drafted = em0.get("status") == "drafted" and bool(em0.get("body"))
            subject = str(em0.get("subject") or fill(s["subject"], values))[:200] if drafted else fill(s["subject"], values)[:200]
            body = str(em0["body"]) if drafted else fill(s["body"], values)
            kind = "first"
        else:
            if not s["followUps"] or d.get("stage") != "applied" or addr in inbox_from:
                continue
            kind = next((k for k, (prev, days) in FOLLOW.items() if (jid, k) not in sent and (jid, prev) in sent
                         and sent[(jid, prev)]["status"] == "sent" and (_ts(sent[(jid, "first")]["sent_at"]) or now) <= now - timedelta(days=days)), "")
            if not kind:
                continue
            subject = "Re: " + sent[(jid, "first")]["subject"]
            body = fill(s["followUp"], values)
        subject = re.sub(r"\s+", " ", subject).strip()  # a header can't hold line breaks
        if re.search(r"\{\w+\}", subject + body) or not subject:
            continue  # a placeholder had no value: don't send a half-filled email
        row = {"id": repo.new_id(), "user_id": uid, "job_id": jid, "kind": kind, "to_addr": addr, "to_source": src[:500],
               "subject": subject, "body": body + footer(cfg, me["my_name"], addr), "status": "queued", "created_at": now_iso()}
        cur = c.execute("INSERT INTO outreach_sends(id, user_id, job_id, kind, to_addr, to_source, subject, body, status, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        tuple(row[k] for k in ("id", "user_id", "job_id", "kind", "to_addr", "to_source", "subject", "body", "status", "created_at")))
        if cur.rowcount:
            queued.append(row)
            room -= 1
            if kind == "first":
                recent_to.add(addr)
    return queued


# ---------------------------------------------------------------- delivery
def deliver(db: Database, cfg: Config, uid: str, send=mailbox.send, token=mailbox.access_token, log=print) -> dict:
    """Send this account's queued emails. A row is marked 'sending' before the call, so a crash can't double-send."""
    out = {"sent": 0, "failed": 0}
    with db.tx() as c:
        box = mailbox_row(c, uid)
        user = c.one("SELECT id, name FROM users WHERE id = ?", (uid,))
        rows = c.all("SELECT * FROM outreach_sends WHERE user_id = ? AND status = 'queued' ORDER BY created_at LIMIT 25", (uid,))
        firsts = {r["job_id"]: r for r in c.all("SELECT job_id, thread_id, message_id FROM outreach_sends WHERE user_id = ? AND kind = 'first' AND status = 'sent'", (uid,))}
    if not box or not rows:
        return out
    try:
        access = token(refresh_token(cfg, box), cfg.google_client_id, cfg.google_client_secret)
    except Exception as e:  # noqa: BLE001 - revoked or expired permission: stop and tell the person
        with db.tx() as c:
            c.execute("UPDATE mailboxes SET last_error = ?, updated_at = ? WHERE user_id = ?", (str(e)[:300], now_iso(), uid))
        log(f"autosend {uid}: no access token: {e}")
        return out
    for r in rows:
        with db.tx() as c:
            if opted_out(c, r["to_addr"]):
                c.execute("UPDATE outreach_sends SET status = 'cancelled', error = 'The recipient opted out.' WHERE id = ?", (r["id"],))
                continue
            claimed = c.execute("UPDATE outreach_sends SET status = 'sending' WHERE id = ? AND status = 'queued'", (r["id"],)).rowcount
        if not claimed:
            continue
        first = firsts.get(r["job_id"]) if r["kind"] != "first" else None
        try:
            raw, mid = mailbox.build(box["address"], (user or {}).get("name") or "", r["to_addr"], r["subject"], r["body"],
                                     unsubscribe=optout_url(cfg, r["to_addr"]), in_reply_to=(first or {}).get("message_id") or "")
        except Exception as e:  # noqa: BLE001 - nothing was sent; record it and carry on with the rest
            with db.tx() as c:
                c.execute("UPDATE outreach_sends SET status = 'failed', error = ? WHERE id = ?", (f"Couldn't build the email: {e}"[:300], r["id"]))
            out["failed"] += 1
            continue
        try:
            res = send(access, raw, (first or {}).get("thread_id") or "")
        except mailbox.MailError as e:
            # 4xx: Gmail refused it, so it wasn't sent. Anything else may have gone out: never retry it.
            status = "failed" if 400 <= e.status < 500 else "unknown"
            with db.tx() as c:
                c.execute("UPDATE outreach_sends SET status = ?, error = ? WHERE id = ?", (status, str(e)[:300], r["id"]))
            out["failed"] += 1
            continue
        with db.tx() as c:
            c.execute("UPDATE outreach_sends SET status = 'sent', sent_at = ?, thread_id = ?, message_id = ? WHERE id = ?",
                      (now_iso(), res.get("threadId") or "", mid, r["id"]))
            doc = repo.get_doc(c, uid, "jobs", r["job_id"])
            if doc:
                d = doc["data"]
                o = dict(d.get("outreach") or {})
                em = dict(o.get("email") or {})
                if r["kind"] == "first":
                    em.update({"status": "sent", "auto": True, "to": r["to_addr"], "subject": r["subject"], "sentAt": now_iso()})
                label = {"first": "Emailed", "follow1": "Day 7 follow-up emailed to", "follow2": "Day 14 follow-up emailed to"}[r["kind"]]
                repo.update_doc(c, uid, "jobs", r["job_id"], {"outreach": dict(o, email=em),
                                                             "timeline": repo.append_timeline(d, f"{label} {r['to_addr']} automatically, from your Gmail")})
            repo.audit(c, uid, "email-sent", "", {"job": r["job_id"], "kind": r["kind"]})
        out["sent"] += 1
    return out


def run(db: Database, cfg: Config, log=print, now: datetime | None = None, **kw) -> dict:
    """The worker's pass: plan and send for every account with a connected mailbox."""
    total = {"queued": 0, "sent": 0, "failed": 0}
    with db.tx() as c:
        users = c.all("SELECT u.id, u.name, u.email, u.is_admin FROM users u JOIN mailboxes m ON m.user_id = u.id WHERE u.disabled_at IS NULL")
    for u in users:
        with db.tx() as c:
            total["queued"] += len(plan_user(c, cfg, u, now))
        r = deliver(db, cfg, u["id"], log=log, **kw)
        total["sent"] += r["sent"]
        total["failed"] += r["failed"]
    return total


def view(c: Conn, cfg: Config, user: dict) -> dict:
    uid = user["id"]
    s = settings(c, uid)
    box = mailbox_row(c, uid)
    plan = plans.plan_of(c, user)
    rows = c.all("SELECT id, job_id, kind, to_addr, to_source, subject, status, error, created_at, sent_at FROM outreach_sends "
                 "WHERE user_id = ? ORDER BY created_at DESC LIMIT 60", (uid,))
    day = now_iso(timedelta(hours=-24))
    return {"available": cfg.gmail_enabled, "mailbox": {"address": box["address"], "connectedAt": box["connected_at"], "error": box["last_error"]} if box else None,
            "on": s["on"], "followUps": s["followUps"], "timezone": s["timezone"], "approved": s["approvedAt"] == template_hash(s), "templateHash": template_hash(s),
            "template": {k: s[k] for k in ("subject", "body", "followUp")}, "defaults": DEFAULT_TEMPLATE,
            "perDay": plans.plan_info(cfg, plan)["autoEmailsPerDay"],
            "last24h": sum(1 for r in rows if r["status"] in ("sent", "sending", "queued") and r["created_at"] > day),
            "sends": [{"id": r["id"], "jobId": r["job_id"], "kind": r["kind"], "to": r["to_addr"], "source": r["to_source"], "subject": r["subject"],
                       "status": r["status"], "error": r["error"], "at": r["sent_at"] or r["created_at"]} for r in rows]}
