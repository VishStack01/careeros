"""Outgoing email: SMTP in production, an in-memory outbox in development and tests.

SMTP_URL forms:
  smtp://user:pass@host:587      STARTTLS (the usual submission port)
  smtps://user:pass@host:465     implicit TLS
  console://                     print to the log (development only)
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from urllib.parse import unquote, urlparse

log = logging.getLogger("careeros.mail")
OUTBOX: list[dict] = []  # development and tests read sent mail here


class Mailer:
    def __init__(self, smtp_url: str, mail_from: str):
        self.url, self.mail_from = smtp_url or "console://", mail_from

    def send(self, to: str, subject: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.mail_from, to, subject
        msg["Message-ID"] = make_msgid(domain=(self.mail_from.rsplit("@", 1)[-1].strip("> ") or "localhost"))
        msg.set_content(text)
        u = urlparse(self.url)
        if u.scheme == "console":
            OUTBOX.append({"to": to, "subject": subject, "text": text})
            log.warning("console mail (development only, not sent) to=%s subject=%r\n%s", to, subject, text)
            return
        ctx = ssl.create_default_context()
        if u.scheme == "smtps":
            server = smtplib.SMTP_SSL(u.hostname, u.port or 465, context=ctx, timeout=20)
        elif u.scheme == "smtp":
            server = smtplib.SMTP(u.hostname, u.port or 587, timeout=20)
            server.starttls(context=ctx)
        else:
            raise ValueError("SMTP_URL must start with smtp://, smtps:// or console://")
        with server:
            if u.username:
                server.login(unquote(u.username), unquote(u.password or ""))
            server.send_message(msg)


def verify_email(name: str, link: str) -> tuple[str, str]:
    return ("Confirm your email for CareerOS",
            f"Hi {name or 'there'},\n\nConfirm your email to finish creating your CareerOS account:\n\n{link}\n\n"
            "The link works once and expires in 24 hours. If you didn't sign up, ignore this email.\n")


def already_registered(link: str) -> tuple[str, str]:
    return ("You already have a CareerOS account",
            "Someone (probably you) tried to sign up with this email, but it already has an account.\n\n"
            f"Sign in, or reset your password here:\n\n{link}\n\nIf this wasn't you, you can ignore this email.\n")


def reset_password(link: str) -> tuple[str, str]:
    return ("Reset your CareerOS password",
            f"Use this link to choose a new password:\n\n{link}\n\n"
            "It works once and expires in 1 hour. Resetting signs you out everywhere. "
            "If you didn't ask for this, ignore this email; your password stays the same.\n")


def password_changed() -> tuple[str, str]:
    return ("Your CareerOS password was changed",
            "Your password was just changed and every session was signed out.\n\n"
            "If this wasn't you, reset your password now from the sign-in page.\n")
