"""Send email from the person's own Gmail (OAuth, scope gmail.send only).

Propelo never reads the mailbox through this connection: the only permission asked for is
"send email on your behalf". The refresh token is encrypted with SECRETS_KEY and can be
removed at any time from Settings, which also revokes it at Google.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Callable

AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REVOKE = "https://oauth2.googleapis.com/revoke"
SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SCOPES = "openid email https://www.googleapis.com/auth/gmail.send"


class MailError(RuntimeError):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


def _call(url: str, data: bytes | None, headers: dict, timeout: float = 20) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed Google hosts
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            err = body.get("error")
            desc = body.get("error_description") or (err.get("message") if isinstance(err, dict) else err) or ""
        except Exception:  # noqa: BLE001
            desc = ""
        raise MailError(f"Google said {e.code}{': ' + str(desc)[:200] if desc else ''}", e.code) from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise MailError(f"Couldn't reach Google: {e}") from None


def form_post(url: str, fields: dict) -> dict:
    return _call(url, urllib.parse.urlencode(fields).encode(), {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})


def json_post(url: str, body: dict, token: str) -> dict:
    return _call(url, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})


def authorize_url(client_id: str, redirect_uri: str, state: str, login_hint: str = "") -> str:
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state, "scope": SCOPES,
         "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"}
    if login_hint:
        q["login_hint"] = login_hint
    return AUTHORIZE + "?" + urllib.parse.urlencode(q)


def _jwt_claims(token: str) -> dict:
    """Claims of the id_token Google returned straight to us over TLS (no signature check needed for that hop)."""
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError):
        return {}


def exchange(code: str, redirect_uri: str, client_id: str, client_secret: str, post: Callable = form_post) -> dict:
    """{"refresh_token", "address", "scopes"} for an authorization code."""
    r = post(TOKEN, {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                     "client_id": client_id, "client_secret": client_secret})
    claims = _jwt_claims(str(r.get("id_token") or ""))
    if not r.get("refresh_token"):
        raise MailError("Google didn't return a long-lived permission. Remove Propelo under your Google account's third-party access and connect again.")
    if "gmail.send" not in str(r.get("scope", "")):
        raise MailError("Permission to send email wasn't granted. Tick the box for sending email and try again.")
    if not claims.get("email") or claims.get("email_verified") is False:
        raise MailError("Google didn't share a verified address for this account.")
    return {"refresh_token": r["refresh_token"], "address": str(claims["email"]).lower(), "scopes": r.get("scope", "")}


def access_token(refresh_token: str, client_id: str, client_secret: str, post: Callable = form_post) -> str:
    r = post(TOKEN, {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id, "client_secret": client_secret})
    if not r.get("access_token"):
        raise MailError("Google returned no access token.")
    return str(r["access_token"])


def revoke(token: str, post: Callable = form_post) -> None:
    try:
        post(REVOKE, {"token": token})
    except MailError:
        pass  # already revoked or expired: removing it here is what matters


def build(from_addr: str, from_name: str, to: str, subject: str, body: str, unsubscribe: str = "",
          in_reply_to: str = "") -> tuple[str, str]:
    """(base64url raw message, Message-ID). Plain text only: no tracking pixels, no links rewritten."""
    m = EmailMessage()
    m["From"] = formataddr((from_name, from_addr)) if from_name else from_addr
    m["To"] = to
    m["Subject"] = subject
    domain = from_addr.split("@")[-1] or "propelo.local"
    mid = make_msgid(domain=domain)
    m["Message-ID"] = mid
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = in_reply_to
    if unsubscribe:
        m["List-Unsubscribe"] = f"<{unsubscribe}>"
        m["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    m.set_content(body)
    return base64.urlsafe_b64encode(m.as_bytes()).decode().rstrip("="), mid


def send(token: str, raw: str, thread_id: str = "", post: Callable = json_post) -> dict:
    body = {"raw": raw}
    if thread_id:
        body["threadId"] = thread_id
    r = post(SEND, body, token)
    if not r.get("id"):
        raise MailError("Gmail didn't accept the message.")
    return {"id": str(r["id"]), "threadId": str(r.get("threadId") or "")}
