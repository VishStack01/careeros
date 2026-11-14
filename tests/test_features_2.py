"""2.0 features: scam check (shared with the dashboard), saved postings, receipts and plan allowances."""

import json
import re
from pathlib import Path

import pytest

from careeros import evaluation, scamcheck

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_uses_the_same_scam_rules():
    html = (ROOT / "dashboard" / "app.html").read_text(encoding="utf-8")
    js = json.loads(re.search(r"const SCAM_RULES = (\[.*?\]);\n", html).group(1))
    rules = json.loads((ROOT / "careeros" / "data" / "scam_rules.json").read_text(encoding="utf-8"))["rules"]
    assert js == [{k: r[k] for k in ("id", "level", "pattern", "why")} for r in rules]


@pytest.mark.parametrize("text,level,ids", [
    ("We build payment rails. 3+ years of Go. Apply through our careers page.", "ok", []),
    ("Selected candidates must pay a refundable security deposit before joining.", "high", ["fee"]),
    ("Please send your Aadhaar and bank account details to confirm your seat.", "high", ["ids-upfront"]),
    ("Contact our HR on WhatsApp only for the interview.", "caution", ["chat-only"]),
    ("Send your CV to hiring.team2026@gmail.com", "caution", ["free-mail"]),
    ("Apply here: https://forms.gle/abc123", "caution", ["form-site"]),
    ("Urgent hiring! Earn ₹3000 per day. Direct joining, no interview. Ping us on Telegram to apply.", "high", None),
])
def test_scam_check(text, level, ids):
    r = scamcheck.check({"title": "Role", "jd": text})
    assert r["level"] == level
    if ids is not None:
        assert [x["id"] for x in r["reasons"]] == ids
    for x in r["reasons"]:
        assert x["quote"] and x["quote"].lower() in text.lower()


def test_ats_addresses_are_not_free_mail():
    assert scamcheck.check({"jd": "Questions? Write to jobs@greenhouse.io"})["level"] == "ok"


def test_unsafe_postings_are_never_auto_applied():
    job = {"jd": "Pay the registration fee of Rs 999 to confirm.", "evaluation": {"score": 4.6}}
    ok, why = evaluation.apply_gate(job, chosen_by_user=True)
    assert not ok and "unsafe" in why
    assert evaluation.apply_gate({"jd": "A normal posting.", "evaluation": {"score": 4.6}}, chosen_by_user=False) == (True, "")


def _key(cloud, c):
    k = cloud.client()
    k.headers["Authorization"] = "Bearer " + c.post("/api/tokens", json={"name": "pc"}).json()["key"]
    return k


def test_extension_saves_posting_details_and_flags_risk(cloud):
    c = cloud.user()
    k = _key(cloud, c)
    r = k.post("/api/agent/track", json={"url": "https://careers.acme.example/jobs/7", "title": "Data Entry", "company": "Acme", "applied": False,
                                         "jd": "Pay a training fee of Rs 1,500 before you start.", "location": "Pune, MH, IN", "salary": "INR 20000 per month"}).json()
    assert r["created"] and r["stage"] == "found" and r["risk"]["level"] == "high"
    d = c.get(f"/api/d/jobs/{r['id']}").json()["data"]
    assert d["jd"].startswith("Pay a training fee") and d["location"] == "Pune, MH, IN" and d["risk"]["reasons"][0]["id"] == "fee"


def test_receipts_keep_fields_but_never_sensitive_ones(cloud):
    c = cloud.user()
    k = _key(cloud, c)
    c.put("/api/d/jobs/j1", json={"company": "Acme", "title": "Engineer", "url": "https://jobs.lever.co/acme/1", "stage": "approved"})
    assert k.post("/api/agent/jobs/j1/begin", json={}).status_code == 200
    fields = [{"label": "Full name", "value": "Asha Rao", "source": "profile"}, {"label": "Date of birth", "value": "x"},
              {"label": "PAN number", "value": "x"}, {"label": "Why us?", "value": "Because…", "source": "package"}]
    assert k.post("/api/agent/jobs/j1/finish", json={"confirmed": True, "confirmation": "Thanks for applying", "form": "jobs.lever.co", "fields": fields}).status_code == 200
    rec = c.get("/api/d/jobs/j1").json()["data"]["application"]
    assert [f["label"] for f in rec["fields"]] == ["Full name", "Why us?"] and rec["confirmation"] == "Thanks for applying"


def test_copilot_mock_and_linkedin_allowances(cloud, monkeypatch):
    from careeros import llm
    monkeypatch.setenv("CAREEROS_LLM", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-server-key-0000")
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"reply": "ok"})
    cloud.cfg.free_ai_credits = 100
    c = cloud.user()
    for _ in range(10):
        assert c.post("/api/ai", json={"prompt": "q", "json": True, "feature": "copilot"}).status_code == 200
    r = c.post("/api/ai", json={"prompt": "q", "json": True, "feature": "copilot"})
    assert r.status_code == 402 and r.json()["code"] == "plan_limit" and "10 copilot questions" in r.json()["error"]
    assert c.post("/api/ai", json={"prompt": "q", "json": True, "feature": "linkedin"}).status_code == 402
    for _ in range(2):
        assert c.post("/api/ai", json={"prompt": "q", "json": True, "feature": "mock"}).status_code == 200
    assert c.post("/api/ai", json={"prompt": "q", "json": True, "feature": "mock"}).status_code == 402
    assert c.get("/api/billing").json()["features"]["copilot"] == {"used": 10, "limit": 10, "per": "day"}
    admin = cloud.user("admin@example.com")
    admin.post("/api/admin/grant", json={"email": "asha@example.com", "plan": "ultra"})
    assert c.post("/api/ai", json={"prompt": "q", "json": True, "feature": "copilot"}).status_code == 200
    assert c.post("/api/ai", json={"prompt": "q", "json": True, "feature": "linkedin"}).status_code == 200


def test_ultra_auto_apply_month_cap(cloud):
    c = cloud.user()
    k = _key(cloud, c)
    admin = cloud.user("admin@example.com")
    admin.post("/api/admin/grant", json={"email": "asha@example.com", "plan": "ultra"})
    nxt = k.get("/api/agent/next").json()
    assert nxt["monthCap"] == 1000 and nxt["appliedThisMonth"] == 0


def test_hosted_ai_falls_back_to_a_second_provider(cloud, monkeypatch):
    from careeros import llm
    monkeypatch.setenv("CAREEROS_LLM", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-server-key-0000")
    monkeypatch.setenv("CAREEROS_LLM_FALLBACK", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-fallback-0000")
    seen = []

    def complete(prompt, tier="default", system="", max_tokens=4096, json_mode=False, cfg=None, timeout=180, env=None):
        seen.append(cfg.provider)
        if cfg.provider == "anthropic":
            raise llm.LLMError("overloaded")
        return "OK"
    monkeypatch.setattr(llm, "complete", complete)
    c = cloud.user()
    r = c.post("/api/ai", json={"prompt": "hi"})
    assert r.status_code == 200 and r.json()["text"] == "OK" and seen == ["anthropic", "openai"]


def test_security_txt_and_admin_audit(cloud):
    cloud.cfg.support_email = "help@example.com"
    t = cloud.client().get("/.well-known/security.txt")
    assert t.status_code == 200 and "Contact: mailto:help@example.com" in t.text and "Expires:" in t.text
    c = cloud.user()
    admin = cloud.user("admin@example.com")
    assert c.get("/api/admin/audit").status_code == 404  # admin routes stay hidden from other accounts
    admin.post("/api/admin/grant", json={"email": "asha@example.com", "plan": "pro"})
    ev = admin.get("/api/admin/audit?kind=plan-granted").json()["events"]
    assert ev and ev[0]["email"] == "asha@example.com" and ev[0]["detail"]["plan"] == "pro"
    assert (ROOT / "website" / ".well-known" / "security.txt").read_text().startswith("Contact: ")


def test_privacy_page_covers_gmail_and_cookies(cloud):
    t = cloud.client().get("/privacy").text
    assert "Limited Use" in t and "Cookies" in t and "Dodo Payments" in t
