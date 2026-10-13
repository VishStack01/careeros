"""Configuration from environment variables. Every value has a development default;
production refuses to start without the settings that matter (see `check`)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FEED = "https://raw.githubusercontent.com/VishStack01/careeros/feed/feed/"


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _list(name: str) -> list[str]:
    return [x.strip().lower() for x in os.environ.get(name, "").split(",") if x.strip()]


@dataclass
class Config:
    app_env: str = "development"  # development | staging | production
    database_url: str = "sqlite:///data/cloud.db"
    public_url: str = "http://127.0.0.1:8000"
    upload_dir: Path = Path("data/uploads")
    max_upload_mb: int = 5
    user_storage_mb: int = 25
    session_ttl_days: int = 14
    password_iterations: int = 600_000
    smtp_url: str = ""
    mail_from: str = "CareerOS <no-reply@localhost>"
    bootstrap_admin_email: str = ""
    signup_mode: str = "open"  # open | allowlist | closed
    signup_allowlist: list[str] = field(default_factory=list)  # emails or @domains
    feed_url: str = DEFAULT_FEED
    ingest_every_minutes: int = 60
    worker_poll_seconds: int = 5
    worker_lease_minutes: int = 10
    db_pool_min: int = 1
    db_pool_max: int = 10
    trust_proxy: bool = False
    max_docs_per_user: int = 5000
    max_doc_kb: int = 512

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ.get
        return cls(
            app_env=e("APP_ENV", "development").lower(),
            database_url=e("DATABASE_URL", "sqlite:///data/cloud.db"),
            public_url=e("PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"),
            upload_dir=Path(e("UPLOAD_DIR", "data/uploads")),
            max_upload_mb=_int("MAX_UPLOAD_MB", 5),
            user_storage_mb=_int("USER_STORAGE_MB", 25),
            session_ttl_days=_int("SESSION_TTL_DAYS", 14),
            password_iterations=_int("PASSWORD_ITERATIONS", 600_000),
            smtp_url=e("SMTP_URL", ""),
            mail_from=e("MAIL_FROM", "CareerOS <no-reply@localhost>"),
            bootstrap_admin_email=e("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower(),
            signup_mode=e("SIGNUP_MODE", "open").lower(),
            signup_allowlist=_list("SIGNUP_ALLOWLIST"),
            feed_url=e("FEED_URL", DEFAULT_FEED),
            ingest_every_minutes=_int("INGEST_EVERY_MINUTES", 60),
            worker_poll_seconds=_int("WORKER_POLL_SECONDS", 5),
            worker_lease_minutes=_int("WORKER_LEASE_MINUTES", 10),
            db_pool_min=_int("DB_POOL_MIN", 1),
            db_pool_max=_int("DB_POOL_MAX", 10),
            trust_proxy=e("TRUST_PROXY", "0") in ("1", "true", "yes"),
            max_docs_per_user=_int("MAX_DOCS_PER_USER", 5000),
            max_doc_kb=_int("MAX_DOC_KB", 512),
        )

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def is_production(self) -> bool:
        return self.app_env in ("production", "staging")

    def check(self) -> list[str]:
        """Problems that make this configuration unsafe to serve real users."""
        if not self.is_production:
            return []
        problems = []
        if not self.database_url.startswith(("postgres://", "postgresql://")):
            problems.append("DATABASE_URL must point at PostgreSQL in staging and production.")
        if not self.public_url.startswith("https://"):
            problems.append("PUBLIC_URL must be an https:// address in staging and production.")
        if not self.smtp_url:
            problems.append("SMTP_URL is required: sign-up and password reset send email.")
        if self.password_iterations < 310_000:
            problems.append("PASSWORD_ITERATIONS must be at least 310000.")
        if self.signup_mode not in ("open", "allowlist", "closed"):
            problems.append("SIGNUP_MODE must be open, allowlist or closed.")
        if "change_me" in self.database_url.lower():
            problems.append("DATABASE_URL still contains the example password.")
        return problems

    def signup_allowed(self, email: str) -> bool:
        if self.signup_mode == "open":
            return True
        if self.signup_mode == "closed":
            return False
        domain = "@" + email.rsplit("@", 1)[-1]
        return email in self.signup_allowlist or domain in self.signup_allowlist
