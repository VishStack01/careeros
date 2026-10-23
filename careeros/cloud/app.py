"""The CareerOS Cloud web app and API (FastAPI).

Pages: /login /signup /forgot /reset /verify (sign-in), / (the dashboard), /privacy, /terms.
API:   /api/auth/*  /api/me*  /api/tokens*  /api/c/<collection>  /api/d/<collection>/<id>
       /api/assets*  /_blob/<id>  /api/agent/*  /api/admin/overview  /api/health  /api/ready

Browser requests are authenticated by an HttpOnly session cookie and must send
the X-CareerOS-CSRF header on writes. The user's apply agent authenticates with
a computer key (Bearer cos_k_...) that can read the pipeline and report results
through /api/agent only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__
from .. import evaluation as evaluation_mod
from .. import followups
from ..dedupe import canonical_url, company_key
from . import mailer as mail
from . import linkedin as li_auth
from . import repo, security
from .config import Config
from .db import Database, now_iso
from .ingest import feed_state
from .mailer import Mailer
from .storage import LocalStorage

log = logging.getLogger("careeros.api")
STATIC = Path(__file__).resolve().parent / "static"
COOKIE = "cos_session"
_DOC_ID = re.compile(r"^[A-Za-z0-9_.:@+~-]{1,200}$")
_ASSET_ID = re.compile(r"^[a-f0-9]{32}$")


@dataclass
class Principal:
    user: dict
    kind: str  # "session" | "key"
    cred_id: str
    token: str

    @property
    def uid(self) -> str:
        return self.user["id"]


def pdf_text(data: bytes, max_pages: int = 8, max_chars: int = 40000) -> str:
    """Best-effort text of an uploaded resume, so the user's agent can read it without the file."""
    try:
        import io

        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        out = []
        for page in reader.pages[:max_pages]:
            out.append(page.extract_text() or "")
            if sum(map(len, out)) > max_chars:
                break
        return re.sub(r"[ \t]+", " ", "\n".join(out)).strip()[:max_chars]
    except Exception:  # noqa: BLE001 - a resume that can't be read as text is still a valid upload
        return ""


def err(status: int, message: str, code: str = "") -> HTTPException:
    return HTTPException(status_code=status, detail={"error": message, "code": code} if code else {"error": message})


def create_app(cfg: Config | None = None, db: Database | None = None) -> FastAPI:
    cfg = cfg or Config.from_env()
    problems = cfg.check()
    if problems:
        raise RuntimeError("Unsafe configuration:\n- " + "\n- ".join(problems))
    db = db or Database(cfg.database_url, cfg.db_pool_min, cfg.db_pool_max)
    if cfg.is_production and db.pending_migrations():
        raise RuntimeError("Database migrations are pending. Run `careeros cloud migrate` before starting the app.")
    if not cfg.is_production:
        db.migrate(log=log.info)
    storage = LocalStorage(cfg.upload_dir)
    mailer = Mailer(cfg.smtp_url, cfg.mail_from)
    app = FastAPI(title="CareerOS Cloud", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg, app.state.db, app.state.storage, app.state.mailer = cfg, db, storage, mailer
    hits: dict[str, deque] = defaultdict(deque)  # per-process API rate limiter

    # ------------------------------------------------------------ helpers
    def client_ip(request: Request) -> str:
        if cfg.trust_proxy:
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else ""

    def send(c, to: str, subject_text: tuple[str, str]) -> None:
        subject, text = subject_text
        if mailer.url.startswith("console"):
            mailer.send(to, subject, text)  # development: straight to the outbox
        else:
            repo.enqueue(c, "send_email", {"to": to, "subject": subject, "text": text}, max_attempts=6)

    def set_session_cookie(response: Response, token: str) -> None:
        response.set_cookie(COOKIE, token, max_age=cfg.session_ttl_days * 86400, httponly=True, secure=cfg.secure_cookies,
                            samesite="lax", path="/")

    def clear_cookie(response: Response) -> None:
        response.delete_cookie(COOKIE, path="/", secure=cfg.secure_cookies, httponly=True, samesite="lax")

    def limited(c, key: str, limit: int, seconds: int) -> None:
        if not security.hit(c, key, limit, seconds):
            raise err(429, "Too many attempts. Wait a few minutes and try again.", "rate_limited")

    def link(path: str, token: str) -> str:
        return f"{cfg.public_url}{path}#token={token}"  # the fragment never reaches server logs

    def principal(request: Request) -> Principal:
        auth = request.headers.get("authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        token = bearer or request.cookies.get(COOKIE, "")
        if not token:
            raise err(401, "Sign in to continue.", "unauthenticated")
        with db.tx() as c:
            if token.startswith("cos_k_"):
                found = repo.api_token_user(c, token)
            elif token.startswith("cos_s_"):
                found = repo.session_user(c, token)
            else:
                found = None
        if not found:
            raise err(401, "Your session has ended. Sign in again.", "unauthenticated")
        user, cred = found
        if not bearer and request.method not in ("GET", "HEAD", "OPTIONS"):
            # Cookie-authenticated writes need the custom header (a cross-site page can't set it
            # without a CORS preflight this server never grants) and, when sent, a matching Origin.
            if request.headers.get("x-careeros-csrf") != "1":
                raise err(403, "Missing CSRF header.", "csrf")
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != cfg.public_url and not cfg.public_url.startswith("http://127.0.0.1"):
                raise err(403, "Cross-site request refused.", "csrf")
        if not user["email_verified_at"]:
            raise err(403, "Confirm your email first.", "unverified")
        key = cred["id"]
        t = time.monotonic()
        if len(hits) > 20000:  # forget idle credentials so the limiter's memory stays bounded
            for k in [k for k, q in hits.items() if not q or q[-1] < t - 300]:
                hits.pop(k, None)
        q = hits[key]
        while q and q[0] < t - 300:
            q.popleft()
        if len(q) >= 1500:
            raise err(429, "Too many requests. Slow down for a minute.", "rate_limited")
        q.append(t)
        return Principal(user=user, kind=cred["kind"], cred_id=cred["id"], token=token)

    def csrf(request: Request) -> None:
        """Auth forms send the header as well, so another site can't sign a visitor in to an account it controls."""
        if request.headers.get("x-careeros-csrf") != "1":
            raise err(403, "Missing CSRF header.", "csrf")

    def session_only(p: Principal = Depends(principal)) -> Principal:
        if p.kind != "session":
            raise err(403, "Computer keys can't do this. Sign in on the dashboard.", "forbidden")
        return p

    def admin_only(p: Principal = Depends(session_only)) -> Principal:
        if not p.user["is_admin"]:
            raise err(404, "Not found.")
        return p

    def check_col(col: str, did: str | None = None) -> None:
        if col not in repo.COLLECTIONS:
            raise err(404, "Not found.")
        if did is not None and not _DOC_ID.match(did):
            raise err(404, "Not found.")

    def html(name: str, nonce: str) -> HTMLResponse:
        text = (STATIC / name).read_text(encoding="utf-8")
        return HTMLResponse(text.replace("<script>", f'<script nonce="{nonce}">'))

    # ------------------------------------------------------------ middleware
    @app.middleware("http")
    async def frame(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:16]
        t0 = time.perf_counter()
        n = request.headers.get("content-length")
        cap = (cfg.max_upload_mb + 1) * 1024 * 1024 if request.url.path.startswith("/api/assets") else (cfg.max_doc_kb + 64) * 1024
        if n and n.isdigit() and int(n) > cap:
            response = JSONResponse({"error": "Request too large."}, status_code=413)
        else:
            request.state.nonce = secrets.token_urlsafe(16)
            response = await call_next(request)
        nonce = getattr(request.state, "nonce", "")
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if cfg.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if not request.url.path.startswith("/_blob/"):
            response.headers["Content-Security-Policy"] = (
                f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'; object-src 'none'")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        log.info(json.dumps({"rid": rid, "method": request.method, "path": request.url.path, "status": response.status_code,
                             "ms": round((time.perf_counter() - t0) * 1000, 1)}))
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        body = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    # ------------------------------------------------------------ pages
    @app.get("/", include_in_schema=False)
    def home(request: Request):
        if not request.cookies.get(COOKIE):
            return RedirectResponse("/login", status_code=303)
        return html("dashboard.html", request.state.nonce)

    @app.get("/app", include_in_schema=False)
    def dashboard(request: Request):
        return home(request)

    def auth_page(request: Request):
        return html("auth.html", request.state.nonce)

    def legal_page(request: Request):
        return html("legal.html", request.state.nonce)

    for path in ("/login", "/signup", "/forgot", "/reset", "/verify"):
        app.add_api_route(path, auth_page, methods=["GET"], include_in_schema=False)
    for path in ("/privacy", "/terms"):
        app.add_api_route(path, legal_page, methods=["GET"], include_in_schema=False)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#000"/>'
               '<path d="M7 21l6-6 5 5 7-9M20 11h5v5" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

    # ------------------------------------------------------------ health
    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "mode": "cloud", "signup": cfg.signup_mode}

    @app.get("/api/ready")
    def ready():
        try:
            pending = db.pending_migrations()
            with db.tx() as c:
                oldest = c.scalar("SELECT MIN(run_after) AS t FROM tasks WHERE status = 'queued'")
                state = feed_state(c)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": type(e).__name__}, status_code=503)
        ok = not pending
        return JSONResponse({"ok": ok, "pendingMigrations": pending, "oldestQueuedTask": oldest,
                             "feedGeneratedAt": state.get("generatedAt"), "lastIngestAt": state.get("ingestedAt")},
                            status_code=200 if ok else 503)

    # ------------------------------------------------------------ auth
    @app.post("/api/auth/signup", status_code=202, dependencies=[Depends(csrf)])
    def signup(request: Request, body: dict = Body(default={})):
        email = security.normalize_email(str(body.get("email", "")))
        password, name = str(body.get("password", "")), str(body.get("name", "")).strip()[:80]
        if not security.valid_email(email):
            raise err(400, "Enter a valid email address.", "email")
        problem = security.password_problem(password, email)
        if problem:
            raise err(400, problem, "password")
        if not cfg.signup_allowed(email):
            raise err(403, "Sign-up is by invitation right now.", "closed")
        ip = client_ip(request)
        pw_hash = security.hash_password(password, cfg.password_iterations)
        with db.tx() as c:
            limited(c, "signup:" + security.ip_key(ip), 10, 3600)
            limited(c, "signup-email:" + hashlib.sha256(email.encode()).hexdigest()[:24], 3, 3600)
            existing = repo.user_by_email(c, email)
            if existing and existing["email_verified_at"]:
                send(c, email, mail.already_registered(f"{cfg.public_url}/forgot"))
            elif existing:
                token = repo.issue_link_token(c, existing["id"], "verify", timedelta(hours=24))
                send(c, email, mail.verify_email(existing["name"], link("/verify", token)))
            else:
                uid = repo.create_user(c, email, name, pw_hash, is_admin=bool(cfg.bootstrap_admin_email) and email == cfg.bootstrap_admin_email)
                token = repo.issue_link_token(c, uid, "verify", timedelta(hours=24))
                send(c, email, mail.verify_email(name, link("/verify", token)))
                repo.audit(c, uid, "signup", ip)
        return {"ok": True, "message": "Check your inbox for a link to confirm your email."}

    @app.post("/api/auth/verify", dependencies=[Depends(csrf)])
    def verify(request: Request, response: Response, body: dict = Body(default={})):
        ip = client_ip(request)
        with db.tx() as c:
            limited(c, "verify:" + security.ip_key(ip), 30, 3600)
        with db.tx() as c:
            uid = repo.consume_link_token(c, str(body.get("token", "")), "verify")
            if not uid:
                raise err(400, "That link has expired or was already used. Sign in to get a new one.", "bad_token")
            c.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?", (now_iso(), now_iso(), uid))
            token = repo.create_session(c, uid, cfg.session_ttl_days, ip, request.headers.get("user-agent", ""))
            repo.enqueue(c, "match_user", user_id=uid, dedupe_key=f"match:{uid}", max_attempts=3)
            repo.audit(c, uid, "email-verified", ip)
            user = repo.user_by_id(c, uid)
        set_session_cookie(response, token)
        return {"ok": True, "user": repo.public_user(user)}

    @app.post("/api/auth/login", dependencies=[Depends(csrf)])
    def login(request: Request, response: Response, body: dict = Body(default={})):
        email = security.normalize_email(str(body.get("email", "")))
        password = str(body.get("password", ""))
        ip = client_ip(request)
        with db.tx() as c:
            limited(c, "login-ip:" + security.ip_key(ip), 30, 900)
            limited(c, "login-email:" + hashlib.sha256(email.encode()).hexdigest()[:24], 10, 900)
            user = repo.user_by_email(c, email)
        if not user:
            security.dummy_verify(cfg.password_iterations)
            raise err(401, "Email or password is incorrect.", "bad_credentials")
        if not security.verify_password(password, user["password_hash"]) or user["disabled_at"]:
            with db.tx() as c:
                repo.audit(c, user["id"], "login-failed", ip)
            raise err(401, "Email or password is incorrect.", "bad_credentials")
        if not user["email_verified_at"]:
            raise err(403, "Confirm your email first. We can send the link again.", "unverified")
        with db.tx() as c:
            if security.needs_rehash(user["password_hash"], cfg.password_iterations):
                c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(password, cfg.password_iterations), user["id"]))
            token = repo.create_session(c, user["id"], cfg.session_ttl_days, ip, request.headers.get("user-agent", ""))
            repo.audit(c, user["id"], "login", ip)
        set_session_cookie(response, token)
        return {"ok": True, "user": repo.public_user(user)}

    # ------------------------------------------------------------ Sign in with LinkedIn (OpenID Connect)
    LI_STATE = "careeros_li_state"

    def li_redirect_uri() -> str:
        return f"{cfg.public_url}/api/auth/linkedin/callback"

    @app.get("/api/auth/providers")
    def auth_providers():
        return {"linkedin": cfg.linkedin_enabled}

    @app.get("/api/auth/linkedin/start")
    def linkedin_start():
        if not cfg.linkedin_enabled:
            raise err(404, "Sign in with LinkedIn isn't set up on this server.", "not_configured")
        state = secrets.token_urlsafe(24)
        resp = RedirectResponse(li_auth.authorize_url(cfg.linkedin_client_id, li_redirect_uri(), state), status_code=303)
        resp.set_cookie(LI_STATE, state, max_age=600, httponly=True, secure=cfg.secure_cookies, samesite="lax", path="/api/auth/linkedin")
        return resp

    @app.get("/api/auth/linkedin/callback")
    def linkedin_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        def back(msg: str):
            resp = RedirectResponse(f"/login#error={msg}", status_code=303)
            resp.delete_cookie(LI_STATE, path="/api/auth/linkedin")
            return resp
        if not cfg.linkedin_enabled:
            raise err(404, "Sign in with LinkedIn isn't set up on this server.", "not_configured")
        expected = request.cookies.get(LI_STATE, "")
        if error or not code or not expected or not secrets.compare_digest(expected, state):
            return back("linkedin_cancelled" if error else "linkedin_state")
        ip = client_ip(request)
        with db.tx() as c:
            limited(c, "linkedin:" + security.ip_key(ip), 30, 3600)
        try:
            info = li_auth.userinfo(li_auth.exchange(code, li_redirect_uri(), cfg.linkedin_client_id, cfg.linkedin_client_secret))
        except Exception:  # noqa: BLE001  a refused or expired code
            return back("linkedin_failed")
        email = security.normalize_email(str(info.get("email") or ""))
        if not security.valid_email(email) or info.get("email_verified") is False:
            return back("linkedin_no_email")
        name = str(info.get("name") or "").strip()[:80]
        with db.tx() as c:
            user = repo.user_by_email(c, email)
            if user and user["disabled_at"]:
                return back("disabled")
            if not user:
                if not cfg.signup_allowed(email):
                    return back("closed")
                # No password: this account signs in with LinkedIn (or sets one through "Forgot password").
                uid = repo.create_user(c, email, name, "!linkedin", is_admin=bool(cfg.bootstrap_admin_email) and email == cfg.bootstrap_admin_email)
                repo.enqueue(c, "match_user", user_id=uid, dedupe_key=f"match:{uid}", max_attempts=3)
                repo.audit(c, uid, "signup-linkedin", ip)
            else:
                uid = user["id"]
            c.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?", (now_iso(), now_iso(), uid))
            token = repo.create_session(c, uid, cfg.session_ttl_days, ip, request.headers.get("user-agent", ""))
            repo.audit(c, uid, "login-linkedin", ip)
        resp = RedirectResponse("/app", status_code=303)
        resp.delete_cookie(LI_STATE, path="/api/auth/linkedin")
        set_session_cookie(resp, token)
        return resp

    @app.post("/api/auth/resend", status_code=202, dependencies=[Depends(csrf)])
    def resend(request: Request, body: dict = Body(default={})):
        email = security.normalize_email(str(body.get("email", "")))
        with db.tx() as c:
            limited(c, "resend:" + security.ip_key(client_ip(request)), 10, 3600)
            limited(c, "resend-email:" + hashlib.sha256(email.encode()).hexdigest()[:24], 3, 3600)
            user = repo.user_by_email(c, email)
            if user and not user["email_verified_at"]:
                token = repo.issue_link_token(c, user["id"], "verify", timedelta(hours=24))
                send(c, email, mail.verify_email(user["name"], link("/verify", token)))
        return {"ok": True, "message": "If that account needs confirming, a new link is on its way."}

    @app.post("/api/auth/forgot", status_code=202, dependencies=[Depends(csrf)])
    def forgot(request: Request, body: dict = Body(default={})):
        email = security.normalize_email(str(body.get("email", "")))
        with db.tx() as c:
            limited(c, "forgot:" + security.ip_key(client_ip(request)), 10, 3600)
            limited(c, "forgot-email:" + hashlib.sha256(email.encode()).hexdigest()[:24], 3, 3600)
            user = repo.user_by_email(c, email)
            if user and not user["disabled_at"]:
                token = repo.issue_link_token(c, user["id"], "reset", timedelta(hours=1))
                send(c, email, mail.reset_password(link("/reset", token)))
        return {"ok": True, "message": "If an account uses that email, a reset link is on its way."}

    @app.post("/api/auth/reset", dependencies=[Depends(csrf)])
    def reset(request: Request, response: Response, body: dict = Body(default={})):
        password, ip = str(body.get("password", "")), client_ip(request)
        with db.tx() as c:
            limited(c, "reset:" + security.ip_key(ip), 20, 3600)
        with db.tx() as c:
            uid = repo.consume_link_token(c, str(body.get("token", "")), "reset")
            if not uid:
                raise err(400, "That link has expired or was already used. Ask for a new one.", "bad_token")
            user = repo.user_by_id(c, uid)
            problem = security.password_problem(password, user["email"])
            if problem:
                raise err(400, problem, "password")
            now = now_iso()
            c.execute("UPDATE users SET password_hash = ?, password_changed_at = ?, email_verified_at = COALESCE(email_verified_at, ?), updated_at = ? WHERE id = ?",
                      (security.hash_password(password, cfg.password_iterations), now, now, now, uid))
            repo.revoke_all_sessions(c, uid)
            token = repo.create_session(c, uid, cfg.session_ttl_days, ip, request.headers.get("user-agent", ""))
            send(c, user["email"], mail.password_changed())
            repo.audit(c, uid, "password-reset", ip)
        set_session_cookie(response, token)
        return {"ok": True}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE, "")
        if token and request.headers.get("x-careeros-csrf") == "1":
            with db.tx() as c:
                repo.revoke_session(c, token)
        clear_cookie(response)
        return {"ok": True}

    # ------------------------------------------------------------ me
    @app.get("/api/me")
    def me(p: Principal = Depends(principal)):
        with db.tx() as c:
            used = repo.storage_used(c, p.uid)
            state = feed_state(c)
        return dict(repo.public_user(p.user), via=p.kind, storage={"usedBytes": used, "quotaBytes": cfg.user_storage_mb * 1024 * 1024},
                    feed={"generatedAt": state.get("generatedAt"), "inventory": state.get("records"), "companies": state.get("companies")})

    @app.patch("/api/me")
    def update_me(body: dict = Body(default={}), p: Principal = Depends(session_only)):
        name = str(body.get("name", p.user["name"])).strip()[:80]
        with db.tx() as c:
            c.execute("UPDATE users SET name = ?, updated_at = ? WHERE id = ?", (name, now_iso(), p.uid))
        return {"ok": True}

    @app.post("/api/me/password")
    def change_password(request: Request, body: dict = Body(default={}), p: Principal = Depends(session_only)):
        if not security.verify_password(str(body.get("current", "")), p.user["password_hash"]):
            raise err(400, "Your current password is incorrect.", "bad_credentials")
        new = str(body.get("new", ""))
        problem = security.password_problem(new, p.user["email"])
        if problem:
            raise err(400, problem, "password")
        with db.tx() as c:
            now = now_iso()
            c.execute("UPDATE users SET password_hash = ?, password_changed_at = ?, updated_at = ? WHERE id = ?",
                      (security.hash_password(new, cfg.password_iterations), now, now, p.uid))
            repo.revoke_all_sessions(c, p.uid, except_id=p.cred_id)
            send(c, p.user["email"], mail.password_changed())
            repo.audit(c, p.uid, "password-changed", client_ip(request))
        return {"ok": True}

    @app.post("/api/me/logout-all")
    def logout_all(response: Response, p: Principal = Depends(session_only)):
        with db.tx() as c:
            repo.revoke_all_sessions(c, p.uid)
            repo.audit(c, p.uid, "logout-all")
        clear_cookie(response)
        return {"ok": True}

    @app.get("/api/me/export")
    def export(request: Request, p: Principal = Depends(session_only)):
        with db.tx() as c:
            data = {
                "exportedAt": now_iso(), "account": repo.public_user(p.user),
                "documents": {col: repo.list_docs(c, p.uid, col) for col in sorted(repo.COLLECTIONS)},
                "files": [dict(a, download=f"{cfg.public_url}/_blob/{a['id']}") for a in repo.list_assets(c, p.uid)],
                "applications": c.all("SELECT job_id, state, attempts, receipt, created_at, updated_at FROM applications WHERE user_id = ?", (p.uid,)),
                "computerKeys": repo.list_api_tokens(c, p.uid),
                "sessions": c.all("SELECT created_at, last_seen_at, expires_at, revoked_at, user_agent FROM sessions WHERE user_id = ?", (p.uid,)),
                "securityEvents": c.all("SELECT at, kind, detail FROM audit_events WHERE user_id = ? ORDER BY at", (p.uid,)),
            }
            repo.audit(c, p.uid, "export", client_ip(request))
        return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="careeros-export.json"'})

    @app.post("/api/me/delete")
    def delete_account(response: Response, body: dict = Body(default={}), p: Principal = Depends(session_only)):
        if str(body.get("confirm", "")) != "DELETE" or not security.verify_password(str(body.get("password", "")), p.user["password_hash"]):
            raise err(400, "Type DELETE and enter your password to delete your account.", "confirm")
        with db.tx() as c:
            c.execute("DELETE FROM users WHERE id = ?", (p.uid,))  # cascades to every per-user table
        storage.delete_user(p.uid)
        log.info(json.dumps({"event": "account-deleted"}))
        clear_cookie(response)
        return {"ok": True}

    # ------------------------------------------------------------ computer keys
    @app.get("/api/tokens")
    def tokens(p: Principal = Depends(session_only)):
        with db.tx() as c:
            return {"keys": repo.list_api_tokens(c, p.uid)}

    @app.post("/api/tokens", status_code=201)
    def new_key(request: Request, body: dict = Body(default={}), p: Principal = Depends(session_only)):
        name = str(body.get("name", "")).strip()[:60] or "My computer"
        with db.tx() as c:
            if len(repo.list_api_tokens(c, p.uid)) >= 5:
                raise err(400, "You have 5 computer keys. Remove one first.", "limit")
            token, meta = repo.create_api_token(c, p.uid, name)
            repo.audit(c, p.uid, "key-created", client_ip(request), {"key": meta["prefix"]})
        return {"key": token, **meta}

    @app.delete("/api/tokens/{tid}")
    def remove_key(tid: str, request: Request, p: Principal = Depends(session_only)):
        with db.tx() as c:
            if not repo.revoke_api_token(c, p.uid, tid):
                raise err(404, "Not found.")
            repo.audit(c, p.uid, "key-revoked", client_ip(request))
        return {"ok": True}

    # ------------------------------------------------------------ documents (the dashboard's data)
    @app.get("/api/c/{col}")
    def list_collection(col: str, request: Request, p: Principal = Depends(principal)):
        check_col(col)
        with db.tx() as c:
            tag = repo.docs_etag(c, p.uid, col)
            if request.headers.get("if-none-match") == tag:
                return Response(status_code=304, headers={"ETag": tag, "Cache-Control": "no-cache"})
            docs = repo.list_docs(c, p.uid, col)
        return JSONResponse({"docs": docs}, headers={"ETag": tag, "Cache-Control": "no-cache"})

    @app.get("/api/d/{col}/{did}")
    def get_document(col: str, did: str, p: Principal = Depends(principal)):
        check_col(col, did)
        with db.tx() as c:
            doc = repo.get_doc(c, p.uid, col, did)
        if not doc:
            raise err(404, "Not found.")
        return doc

    def _validate_body(body) -> dict:
        if not isinstance(body, dict):
            raise err(400, "The document must be a JSON object.", "invalid_argument")
        if len(json.dumps(body)) > cfg.max_doc_kb * 1024:
            raise err(413, "That document is too large.", "too_large")
        return body

    def _after_write(c, uid: str, col: str, did: str) -> None:
        if col == "settings" and did == "profile":
            repo.enqueue(c, "match_user", user_id=uid, dedupe_key=f"match:{uid}", delay_seconds=15, max_attempts=3)

    def _if_version(request: Request) -> int | None:
        v = request.headers.get("if-match", "")
        return int(v) if v.isdigit() else None

    @app.put("/api/d/{col}/{did}")
    def put_document(col: str, did: str, request: Request, body: dict = Body(default={}), p: Principal = Depends(session_only)):
        check_col(col, did)
        _validate_body(body)
        with db.tx() as c:
            if not repo.get_doc(c, p.uid, col, did) and repo.count_docs(c, p.uid) >= cfg.max_docs_per_user:
                raise err(400, "Your account has reached its document limit.", "quota")
            try:
                version = repo.set_doc(c, p.uid, col, did, body, _if_version(request))
            except ValueError as e:
                raise err(409, str(e), "conflict") from e
            _after_write(c, p.uid, col, did)
        return {"version": version}

    @app.patch("/api/d/{col}/{did}")
    def patch_document(col: str, did: str, request: Request, body: dict = Body(default={}), p: Principal = Depends(session_only)):
        check_col(col, did)
        _validate_body(body)
        with db.tx() as c:
            try:
                version = repo.update_doc(c, p.uid, col, did, body, _if_version(request))
            except KeyError as e:
                raise err(404, "Not found.") from e
            except ValueError as e:
                raise err(409, str(e), "conflict") from e
            _after_write(c, p.uid, col, did)
        return {"version": version}

    @app.delete("/api/d/{col}/{did}")
    def delete_document(col: str, did: str, p: Principal = Depends(session_only)):
        check_col(col, did)
        with db.tx() as c:
            repo.delete_doc(c, p.uid, col, did)
        return {"ok": True}

    # ------------------------------------------------------------ files
    @app.get("/api/assets")
    def assets(p: Principal = Depends(session_only)):
        with db.tx() as c:
            return {"assets": repo.list_assets(c, p.uid), "usage": {"usedBytes": repo.storage_used(c, p.uid),
                                                                     "quotaBytes": cfg.user_storage_mb * 1024 * 1024}}

    @app.post("/api/assets", status_code=201)
    async def upload(request: Request, p: Principal = Depends(principal)):
        cap = cfg.max_upload_mb * 1024 * 1024
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > cap:
                raise err(413, f"Files can be up to {cfg.max_upload_mb} MB.", "too_large")
        data = bytes(data)
        if not data.startswith(b"%PDF-"):
            raise err(415, "Only PDF files can be uploaded.", "unsupported_type")
        name = re.sub(r"[^\w .()-]+", "_", request.query_params.get("name", "resume.pdf"))[:120] or "resume.pdf"

        def save():
            with db.tx() as c:
                if repo.storage_used(c, p.uid) + len(data) > cfg.user_storage_mb * 1024 * 1024:
                    raise err(413, "Your storage is full. Remove an old file first.", "quota")
                aid = security.new_id()
                key = storage.put(p.uid, aid, "pdf", data)
                c.execute("INSERT INTO assets(id, user_id, name, content_type, size_bytes, sha256, storage_key, text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (aid, p.uid, name, "application/pdf", len(data), hashlib.sha256(data).hexdigest(), key, pdf_text(data), now_iso()))
                return {"id": aid, "url": f"/_blob/{aid}", "sizeBytes": len(data), "contentType": "application/pdf", "name": name}
        return await run_in_threadpool(save)

    @app.delete("/api/assets/{aid}")
    def delete_asset(aid: str, p: Principal = Depends(session_only)):
        with db.tx() as c:
            a = repo.get_asset(c, p.uid, aid) if _ASSET_ID.match(aid) else None
            if not a:
                raise err(404, "Not found.")
            c.execute("DELETE FROM assets WHERE id = ? AND user_id = ?", (aid, p.uid))
        storage.delete(a["storage_key"])
        return {"ok": True}

    @app.get("/_blob/{aid}")
    def blob(aid: str, p: Principal = Depends(principal)):
        with db.tx() as c:
            a = repo.get_asset(c, p.uid, aid) if _ASSET_ID.match(aid) else None
        if not a:
            raise err(404, "Not found.")
        safe = re.sub(r'[^\w .()-]', "_", a["name"])
        return Response(storage.get(a["storage_key"]), media_type=a["content_type"],
                        headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "private, no-store"})

    # ------------------------------------------------------------ the user's apply agent
    def _job(c, uid: str, jid: str) -> dict:
        doc = repo.get_doc(c, uid, "jobs", jid) if _DOC_ID.match(jid) else None
        if not doc:
            raise err(404, "Not found.")
        return doc

    def _app_key(d: dict) -> str:
        basis = company_key(d.get("company", "")) + "|" + (canonical_url(d.get("url", "")) or d.get("title", ""))
        return hashlib.sha256(basis.encode()).hexdigest()[:24]

    @app.get("/api/agent/next")
    def agent_next(limit: int = 8, p: Principal = Depends(principal)):
        with db.tx() as c:
            settings = (repo.get_doc(c, p.uid, "settings", "profile") or {"data": {}})["data"]
            jobs = repo.list_docs(c, p.uid, "jobs")
            recent = {r["company_key"] for r in c.all("SELECT company_key FROM applications WHERE user_id = ? AND state = 'submitted' AND updated_at > ?",
                                                      (p.uid, now_iso(timedelta(days=-180))))}
            applicant = repo.get_doc(c, p.uid, "profile", "applicant")
        tz = ZoneInfo(str(settings.get("timezone") or "Asia/Kolkata"))
        today = datetime.now(tz).date()

        def local_day(s):
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(tz).date()
            except (ValueError, AttributeError):
                return None
        cap = int(settings.get("dailyCap") or 8)
        done_today = sum(1 for j in jobs if local_day(j["data"].get("appliedAt") or "") == today)
        recent |= {company_key(j["data"].get("company", "")) for j in jobs if j["data"].get("appliedAt")}
        left = max(0, cap - done_today)
        auto = settings.get("approvalMode") == "auto-when-clear"
        order = {"remote-global": 0, "remote-india": 1, "south-india": 2}
        groups = {"queued": [], "approved": [], "auto": []}
        for j in jobs:
            d = j["data"]
            if d.get("appliedAt") or d.get("stage") in ("skipped", "applied", "screen", "interview", "offer", "rejected", "withdrawn") or d.get("needsYou"):
                continue
            if d.get("stage") == "approved":
                groups["queued" if d.get("autoApply") == "queued" else "approved"].append(j)
            elif auto and (d.get("stage") == "ready" or (d.get("stage") in ("found", None, "") and all(ch.get("passed") for ch in d.get("checks") or [{}]))):
                groups["auto"].append(j)

        def key(j):
            d = j["data"]
            try:
                ts = datetime.fromisoformat((d.get("postedAt") or "").replace("Z", "+00:00")).timestamp()
            except ValueError:
                ts = 0
            fresh = (time.time() - ts) < 72 * 3600
            return (0 if fresh else 1, order.get(d.get("region", ""), 9), -ts)
        picked, companies = [], set()
        for g, items in (("queued", sorted(groups["queued"], key=lambda j: j["data"].get("queuedAt") or "")),
                         ("approved", sorted(groups["approved"], key=key)), ("auto", sorted(groups["auto"], key=key))):
            for j in items:
                ck = company_key(j["data"].get("company", ""))
                if ck in companies or (g != "queued" and ck in recent):
                    continue
                if evaluation_mod.apply_gate(j["data"], chosen_by_user=g != "auto")[1].startswith("Scored"):
                    continue  # under the apply line and the user hasn't said "apply anyway"
                companies.add(ck)
                picked.append({"id": j["id"], "version": j["version"], "group": g, **{k: j["data"].get(k) for k in (
                    "company", "title", "url", "region", "postedAt", "location", "workMode", "stage", "checks", "brief", "evidence", "gaps", "score", "scoreOverride")},
                    "needsScore": g == "auto" and not (j["data"].get("evaluation") or {}).get("score")})
        n = min(left, max(0, min(int(limit), 25)))
        res = (applicant or {"data": {}})["data"].get("resume") or {}
        return {"dailyCap": cap, "appliedToday": done_today, "left": left, "approvalMode": settings.get("approvalMode"), "applyLine": evaluation_mod.APPLY_LINE,
                "paused": settings.get("approvalMode") == "paused", "roles": picked[:n],
                "applicantReady": bool(applicant), "resume": {"id": res.get("id"), "name": res.get("name")} if res.get("id") else None}

    @app.get("/api/agent/applicant")
    def agent_applicant(p: Principal = Depends(principal)):
        with db.tx() as c:
            doc = repo.get_doc(c, p.uid, "profile", "applicant")
            brain = repo.get_doc(c, p.uid, "brain", "brain")
            rid = ((doc or {"data": {}})["data"].get("resume") or {}).get("id", "")
            text = c.scalar("SELECT text FROM assets WHERE id = ? AND user_id = ?", (rid, p.uid)) if rid else None
        return {"applicant": doc["data"] if doc else None, "resumeText": text or "", "brain": brain["data"] if brain else None}

    @app.post("/api/agent/brain")
    def agent_brain(body: dict = Body(default={}), p: Principal = Depends(principal)):
        brain, status = body.get("brain"), body.get("status") or {}
        if not isinstance(brain, dict) or not isinstance(status, dict):
            raise err(400, "Send {brain: {...}, status: {...}}.", "invalid_argument")
        _validate_body(brain)
        status = {"state": "ready" if status.get("state") == "ready" else "building", "summary": str(status.get("summary", ""))[:400],
                  "counts": status.get("counts") if isinstance(status.get("counts"), dict) else {}, "updatedAt": now_iso()}
        with db.tx() as c:
            repo.set_doc(c, p.uid, "brain", "brain", brain)
            repo.set_doc(c, p.uid, "brain", "status", status)
        return {"ok": True}

    @app.get("/api/prompts/{name}")
    def prompt(name: str, p: Principal = Depends(session_only)):
        if name not in ("apply", "brain"):
            raise err(404, "Not found.")
        text = (Path(__file__).resolve().parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")
        return {"name": name, "text": text.replace("{{SERVER}}", cfg.public_url)}

    @app.post("/api/agent/heartbeat")
    def agent_heartbeat(body: dict = Body(default={}), p: Principal = Depends(principal)):
        patch = {"linked": True, "lastSeenAt": now_iso(), "device": str(body.get("device", ""))[:80], "browser": str(body.get("browser", ""))[:40],
                 "lastError": "", "via": "computer key" if p.kind == "key" else "dashboard"}
        with db.tx() as c:
            if repo.get_doc(c, p.uid, "settings", "applyRunner"):
                repo.update_doc(c, p.uid, "settings", "applyRunner", patch)
            else:
                repo.set_doc(c, p.uid, "settings", "applyRunner", patch)
        return {"ok": True}

    @app.post("/api/agent/jobs/{jid}/fit")
    def agent_fit(jid: str, body: dict = Body(default={}), p: Principal = Depends(principal)):
        """Record the fit check. With "evaluation" (the scored 1-5 evaluation), it is
        checked first: quotes against "jd" (the posting's text, archived on the role),
        claim ids against the brain. A role the user chose that scores under the apply
        line waits for them; it is never submitted on the agent's say-so."""
        allowed = {k: body[k] for k in ("decision", "fitBand", "decisionReason", "evidence", "gaps") if k in body}
        ev = body.get("evaluation")
        if ev is not None and len(json.dumps(ev)) > 96 * 1024:
            raise err(413, "That evaluation is too large.", "too_large")
        jd = str(body.get("jd") or "")[:60000] or None
        with db.tx() as c:
            d = _job(c, p.uid, jid)["data"]
            if ev is not None:
                brain = (repo.get_doc(c, p.uid, "brain", "brain") or {}).get("data")
                errors, warnings = evaluation_mod.validate(ev, jd=jd or d.get("jd"), brain=brain or None)
                if errors:
                    raise HTTPException(422, detail={"error": "The evaluation didn't pass its checks.", "code": "invalid_evaluation", "problems": errors[:20]})
                norm = evaluation_mod.normalize(ev)
                allowed = evaluation_mod.job_patch(norm, ev.get("decision"))
                if jd and not d.get("jd"):
                    allowed["jd"], allowed["jdArchivedAt"] = jd, now_iso()
                event = f"Scored {norm['score']:.1f}/5: {norm['verdict']['label']}"
                if norm["score"] < evaluation_mod.APPLY_LINE and d.get("stage") == "approved" and not d.get("scoreOverride") and not d.get("appliedAt"):
                    allowed.update({"needsYou": f"Scored {norm['score']:.1f}, under the {evaluation_mod.APPLY_LINE} apply line. {norm.get('summary', '')}".strip()[:400],
                                    "needsYouKind": "score", "needsYouAt": now_iso()})
                allowed["timeline"] = repo.append_timeline(d, event)
                version = repo.update_doc(c, p.uid, "jobs", jid, allowed)
                return {"version": version, "score": norm["score"], "verdict": norm["verdict"], "confidence": norm["confidence"],
                        "apply": evaluation_mod.apply_gate(dict(d, **allowed), chosen_by_user=d.get("stage") == "approved")[0], "warnings": warnings}
            return {"version": repo.update_doc(c, p.uid, "jobs", jid, allowed)}

    @app.post("/api/agent/jobs/{jid}/begin")
    def agent_begin(jid: str, body: dict = Body(default={}), p: Principal = Depends(principal)):
        """Call right before pressing Submit. Refuses a second submission, ever.
        Send {"jd": "<the posting's full text>"} to archive it if /fit didn't."""
        with db.tx() as c:
            d = _job(c, p.uid, jid)["data"]
            jd = str((body or {}).get("jd") or "")[:60000]
            if jd and not d.get("jd"):
                repo.update_doc(c, p.uid, "jobs", jid, {"jd": jd, "jdArchivedAt": now_iso()})
            if d.get("appliedAt"):
                raise err(409, "Already applied to this role.", "already_submitted")
            ok, why = evaluation_mod.apply_gate(d, chosen_by_user=d.get("stage") == "approved")
            if not ok:
                raise err(409, why, "below_apply_line" if why.startswith("Scored") else "needs_evaluation")
            key, now = _app_key(d), now_iso()
            row = c.one("SELECT state FROM applications WHERE user_id = ? AND key = ?", (p.uid, key))
            if row and row["state"] == "submitted":
                raise err(409, "Already applied to this role.", "already_submitted")
            if row and row["state"] == "submitting":
                raise err(409, "A previous attempt may have gone through. The user must check before any retry.", "needs_check")
            c.execute("INSERT INTO applications(user_id, key, job_id, company_key, state, attempts, created_at, updated_at) VALUES (?, ?, ?, ?, 'submitting', 1, ?, ?) "
                      "ON CONFLICT (user_id, key) DO UPDATE SET state = 'submitting', attempts = applications.attempts + 1, updated_at = excluded.updated_at",
                      (p.uid, key, jid, company_key(d.get("company", "")), now, now))
        return {"ok": True, "key": key}

    @app.post("/api/agent/jobs/{jid}/finish")
    def agent_finish(jid: str, body: dict = Body(default={}), p: Principal = Depends(principal)):
        ok = body.get("confirmed") is True
        with db.tx() as c:
            doc = _job(c, p.uid, jid)
            d = doc["data"]
            key = _app_key(d)
            row = c.one("SELECT state FROM applications WHERE user_id = ? AND key = ?", (p.uid, key))
            if not row or row["state"] != "submitting":
                raise err(409, "Call begin before submitting.", "not_started")
            host = str(body.get("form", ""))[:200]
            if ok:
                receipt = {"confirmation": str(body.get("confirmation", ""))[:500], "form": host, "at": now_iso()}
                c.execute("UPDATE applications SET state = 'submitted', receipt = ?, updated_at = ? WHERE user_id = ? AND key = ?",
                          (json.dumps(receipt), now_iso(), p.uid, key))
                patch = {"stage": "applied", "appliedAt": now_iso()[:19] + "Z", "appliedVia": "careeros", "autoApply": "done", "needsYou": "", "needsYouKind": "",
                         "application": receipt, "timeline": repo.append_timeline(d, f"Applied automatically on {host or 'the company site'}")}
                if body.get("resumeAsset"):
                    patch["resume"] = {"asset": str(body["resumeAsset"])[:40], "label": "Resume sent", "version": str(body.get("resumeVersion", "original"))[:20]}
                for k in ("screening", "coverNote"):
                    if k in body:
                        patch[k] = body[k]
                patch["followUps"] = followups.seed(dict(d, **patch))
            else:
                reason = "Submitted, but no confirmation appeared. Check the site or your email before trying again."
                patch = {"needsYou": reason, "needsYouAt": now_iso(), "autoApply": "done", "applyUrl": str(body.get("applyUrl", d.get("url", "")))[:2000],
                         "timeline": repo.append_timeline(d, "Auto-apply: submitted without a confirmation")}
            version = repo.update_doc(c, p.uid, "jobs", jid, patch)
        return {"ok": True, "version": version}

    @app.post("/api/agent/jobs/{jid}/needs-you")
    def agent_needs_you(jid: str, body: dict = Body(default={}), p: Principal = Depends(principal)):
        reason = str(body.get("reason", "")).strip()[:400]
        if not reason:
            raise err(400, "Say why the role needs the user.", "invalid_argument")
        with db.tx() as c:
            d = _job(c, p.uid, jid)["data"]
            version = repo.update_doc(c, p.uid, "jobs", jid, {
                "needsYou": reason, "needsYouAt": now_iso(), "applyUrl": str(body.get("applyUrl", d.get("url", "")))[:2000],
                "timeline": repo.append_timeline(d, f"Auto-apply stopped: {reason}")})
        return {"ok": True, "version": version}

    @app.post("/api/agent/jobs/{jid}/closed")
    def agent_closed(jid: str, p: Principal = Depends(principal)):
        with db.tx() as c:
            d = _job(c, p.uid, jid)["data"]
            version = repo.update_doc(c, p.uid, "jobs", jid, {"stage": "skipped", "autoApply": "done",
                                                               "skip": {"gate": "Closed", "reason": "The posting is closed.", "wouldChange": ""},
                                                               "timeline": repo.append_timeline(d, "Closed: the posting says it's no longer open")})
        return {"ok": True, "version": version}

    @app.post("/api/agent/runs", status_code=201)
    def agent_run(body: dict = Body(default={}), p: Principal = Depends(principal)):
        doc = {"startedAt": str(body.get("startedAt") or now_iso()), "finishedAt": str(body.get("finishedAt") or now_iso()), "kind": "apply",
               "applied": int(body.get("applied") or 0), "needsYou": int(body.get("needsYou") or 0), "summary": str(body.get("summary", ""))[:500]}
        rid = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S") + "-apply"
        with db.tx() as c:
            repo.set_doc(c, p.uid, "runs", rid, doc)
            if repo.get_doc(c, p.uid, "settings", "applyRunner"):
                repo.update_doc(c, p.uid, "settings", "applyRunner", {"lastRunAt": now_iso(), "lastApplied": doc["applied"]})
        return {"ok": True, "id": rid}

    @app.post("/api/applications/{jid}/reset")
    def reset_application(jid: str, p: Principal = Depends(session_only)):
        """The user checked: an uncertain submission did NOT go through, so auto-apply may try again."""
        with db.tx() as c:
            d = _job(c, p.uid, jid)["data"]
            c.execute("UPDATE applications SET state = 'failed', updated_at = ? WHERE user_id = ? AND key = ? AND state = 'submitting'",
                      (now_iso(), p.uid, _app_key(d)))
        return {"ok": True}

    # ------------------------------------------------------------ operators
    @app.get("/api/admin/overview")
    def admin_overview(p: Principal = Depends(admin_only)):
        with db.tx() as c:
            return {
                "users": c.scalar("SELECT COUNT(*) AS n FROM users"),
                "verifiedUsers": c.scalar("SELECT COUNT(*) AS n FROM users WHERE email_verified_at IS NOT NULL"),
                "activeLast7Days": c.scalar("SELECT COUNT(*) AS n FROM users WHERE last_login_at > ?", (now_iso(timedelta(days=-7)),)),
                "activeJobs": c.scalar("SELECT COUNT(*) AS n FROM jobs WHERE active = 1"),
                "feed": feed_state(c),
                "tasks": c.all("SELECT kind, status, COUNT(*) AS n FROM tasks GROUP BY kind, status ORDER BY kind, status"),
                "recentFailures": c.all("SELECT kind, last_error, finished_at FROM tasks WHERE status = 'failed' ORDER BY finished_at DESC LIMIT 10"),
            }

    return app
