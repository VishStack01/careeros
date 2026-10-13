"""Shared fixtures. The cloud fixtures run on SQLite, and on PostgreSQL too when
CAREEROS_TEST_POSTGRES_URL points at a disposable database (its schema is wiped)."""

from __future__ import annotations

import gzip
import json
import os
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

PG_URL = os.environ.get("CAREEROS_TEST_POSTGRES_URL", "")
BACKENDS = ["sqlite"] + (["postgres"] if PG_URL else [])


def make_pdf(text: str = "Asha Example. Python, FastAPI and LLM evaluation. Built a ticket router.") -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def feed_record(i: int, title: str = "", company: str = "", days: int = 1, loc: str = "remote-worldwide", exp: float = 0.0) -> dict:
    posted = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    facts = {"expMin": exp, "fresherOk": exp == 0, "loc": loc, "locQuote": "Remote, anywhere", "salaryLow": 10.0, "salaryHigh": 14.0,
             "salaryQuote": "₹10-14 LPA", "closedQuote": "", "expQuote": f"{exp:g} years"}
    return {"id": f"co{i % 40}-ai-engineer-{i}", "company": company or f"Company {i % 40}", "title": title or f"AI Engineer {i}",
            "url": f"https://jobs.example.com/{i}", "source": "Greenhouse", "location": "Remote", "workMode": "remote", "postedAt": posted,
            "salary": "", "summary": "We build AI agents with Python and LLMs. Freshers welcome.", "via": "careers", "facts": facts}


def write_feed(d, records: list[dict], generated: str | None = None, errored: list[str] | None = None) -> None:
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / "india.jsonl.gz", "wt") as f, gzip.open(d / "full.jsonl.gz", "wt") as g:
        for r in records:
            f.write(json.dumps(r) + "\n")
            g.write(json.dumps({"id": r["id"], "text": r["summary"] + " Full posting text."}) + "\n")
    (d / "summary.json").write_text(json.dumps({"generatedAt": generated or datetime.now(timezone.utc).isoformat(), "boards": 3, "companies": 40,
                                                "openings": len(records), "remoteBoards": {"x": 1}, "erroredCompanies": errored or []}))


def _reset_postgres(url: str) -> None:
    import psycopg
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


@pytest.fixture(params=BACKENDS)
def cloud(request, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from careeros.cloud.app import create_app
    from careeros.cloud.config import Config
    from careeros.cloud.mailer import OUTBOX

    if request.param == "postgres":
        _reset_postgres(PG_URL)
        url = PG_URL
    else:
        url = f"sqlite:///{tmp_path}/cloud.db"
    cfg = Config(database_url=url, upload_dir=tmp_path / "uploads", password_iterations=1000, public_url="http://testserver",
                 feed_url=str(tmp_path / "feed"), bootstrap_admin_email="admin@example.com", max_upload_mb=1, user_storage_mb=2)
    app = create_app(cfg)
    OUTBOX.clear()

    def client():
        c = TestClient(app)
        c.headers["X-CareerOS-CSRF"] = "1"  # what the sign-in pages and dashboard send
        return c

    def last_token(kind: str = "verify") -> str:
        for m in reversed(OUTBOX):
            found = re.search(rf"/{kind}#token=([\w-]+)", m["text"])
            if found:
                return found.group(1)
        raise AssertionError(f"no {kind} email")

    def user(email: str = "asha@example.com", password: str = "correct horse battery", name: str = "Asha"):
        c = client()
        assert c.post("/api/auth/signup", json={"email": email, "password": password, "name": name}).status_code == 202
        r = c.post("/api/auth/verify", json={"token": last_token()})
        assert r.status_code == 200, r.text
        c.headers["X-CareerOS-CSRF"] = "1"
        c.uid = r.json()["user"]["id"]
        return c

    ns = SimpleNamespace(cfg=cfg, app=app, db=app.state.db, client=client, user=user, last_token=last_token, outbox=OUTBOX, backend=request.param)
    yield ns
    app.state.db.close()
