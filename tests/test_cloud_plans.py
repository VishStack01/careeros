"""Plans, Razorpay billing, AI metering and users' own keys in CareerOS Cloud."""

import hashlib
import hmac
import json
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

SUB = {"id": "sub_TEST1234567890", "short_url": "https://rzp.io/i/abc123", "status": "created"}


@pytest.fixture(autouse=True)
def no_server_model(monkeypatch):
    for k in ("CAREEROS_LLM", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_HOST", "CAREEROS_MODEL"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def fake_model(monkeypatch):
    from careeros import llm
    calls = []

    def complete(prompt, tier="default", system="", max_tokens=4096, json_mode=False, cfg=None, timeout=180, env=None):
        calls.append({"provider": cfg.provider if cfg else None, "base": cfg.base_url if cfg else None, "prompt": prompt})
        if "FAIL" in prompt:
            raise llm.LLMError("model down")
        return '{"ok": true}' if json_mode else "OK"
    monkeypatch.setattr(llm, "complete", complete)
    return calls


def _billing_on(cloud, posts):
    cloud.cfg.razorpay_key_id, cloud.cfg.razorpay_key_secret = "rzp_test_x", "secret"
    cloud.cfg.razorpay_webhook_secret, cloud.cfg.razorpay_plan_pro = "whsec", "plan_TEST1234567890"

    def post(url, body, kid, ksec):
        posts.append((url, body, kid))
        return dict(SUB) if url.endswith("/subscriptions") else {"id": SUB["id"], "status": "active"}
    cloud.app.state.razorpay.post = post


def _hook(cloud, event, eid="evt_1", secret="whsec"):
    body = json.dumps(event).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return cloud.client().post("/api/billing/webhook", content=body,
                               headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": eid})


def _sub_event(kind, status, end=None, at=None, sub_id=None, notes=None):
    ent = {"id": sub_id or SUB["id"], "status": status, "current_end": end or int(time.time()) + 30 * 86400}
    if notes:
        ent["notes"] = notes
    return {"event": kind, "created_at": at or int(time.time()), "payload": {"subscription": {"entity": ent}}}


def test_new_accounts_are_free_and_see_the_catalog(cloud):
    c = cloud.user()
    me = c.get("/api/me").json()
    assert me["plan"] == "free" and me["ai"]["source"] == "none" and me["ai"]["available"] is False
    cat = cloud.client().get("/api/plans").json()
    assert [p["id"] for p in cat["plans"]] == ["free", "pro"] and cat["plans"][1]["priceInr"] == cloud.cfg.pro_price_inr
    assert cat["checkoutEnabled"] is False
    assert c.post("/api/billing/checkout").status_code == 503


def test_hosted_ai_is_metered_by_plan(cloud, monkeypatch, fake_model):
    monkeypatch.setenv("CAREEROS_LLM", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-server-key-0000")
    cloud.cfg.free_ai_credits = 2
    c = cloud.user()
    assert c.get("/api/me").json()["ai"] == pytest.approx(c.get("/api/me").json()["ai"])
    assert c.get("/api/me").json()["ai"]["source"] == "hosted"
    assert c.post("/api/ai", json={"prompt": "hi", "json": True}).json() == {"json": {"ok": True}, "source": "hosted"}
    assert c.post("/api/ai", json={"prompt": "FAIL"}).status_code == 502  # a failed call isn't counted
    assert c.post("/api/ai", json={"prompt": "hi"}).json()["text"] == "OK"
    r = c.post("/api/ai", json={"prompt": "hi"})
    assert r.status_code == 402 and r.json()["code"] == "ai_quota" and "Upgrade to Pro" in r.json()["error"]
    assert c.get("/api/billing").json()["ai"]["left"] == 0
    # computer keys can't spend AI
    k = cloud.client()
    k.headers["Authorization"] = "Bearer " + c.post("/api/tokens", json={"name": "pc"}).json()["key"]
    assert k.post("/api/ai", json={"prompt": "hi"}).status_code == 403


def test_own_key_is_encrypted_and_unmetered(cloud, fake_model):
    c = cloud.user()
    key = "sk-proj-abcdefghijklmnopqrstuvwxyz1234"
    r = c.put("/api/me/ai-key", json={"provider": "openai", "key": key, "baseUrl": "https://openrouter.ai/api/v1"})
    assert r.status_code == 200 and r.json()["ownKey"]["hint"] == "…1234"
    with cloud.db.tx() as t:
        stored = t.one("SELECT secret FROM ai_keys")["secret"]
    assert key not in stored and "abcdefgh" not in stored
    assert key not in json.dumps(c.get("/api/billing").json()) and key not in c.get("/api/me/export").text
    cloud.cfg.free_ai_credits = 0
    for _ in range(3):
        assert c.post("/api/ai", json={"prompt": "hi"}).json()["source"] == "own"
    assert fake_model[-1]["provider"] == "openai" and fake_model[-1]["base"] == "https://openrouter.ai/api/v1"
    assert c.get("/api/billing").json()["ai"]["ownUsed"] == 3
    assert c.post("/api/me/ai-key/test").json()["ok"] is True
    # another account never uses it
    b = cloud.user("bala@example.com")
    assert b.post("/api/ai", json={"prompt": "hi"}).status_code == 503
    assert c.delete("/api/me/ai-key").status_code == 200 and c.get("/api/me").json()["ai"]["ownKey"] is None


@pytest.mark.parametrize("body", [
    {"provider": "openai", "key": "sk-proj-abcdefghijklmnop", "baseUrl": "http://169.254.169.254/latest"},
    {"provider": "openai", "key": "sk-proj-abcdefghijklmnop", "baseUrl": "https://evil.example.com/v1"},
    {"provider": "openai", "key": "sk-proj-abcdefghijklmnop", "baseUrl": "https://api.openai.com:8443/v1"},
    {"provider": "anthropic", "key": "sk-ant-abcdefghijklmnop", "baseUrl": "https://api.openai.com/v1"},
    {"provider": "ollama", "key": "sk-abcdefghijklmnopqrst"},
    {"provider": "openai", "key": "short"},
])
def test_own_key_rejects_unsafe_settings(cloud, body):
    assert cloud.user().put("/api/me/ai-key", json=body).status_code == 400


def test_checkout_webhooks_and_cancel(cloud):
    posts = []
    _billing_on(cloud, posts)
    c = cloud.user()
    r = c.post("/api/billing/checkout")
    assert r.status_code == 200 and r.json()["url"] == SUB["short_url"]
    url, body, kid = posts[0]
    assert url.endswith("/v1/subscriptions") and body["plan_id"] == "plan_TEST1234567890" and body["notes"]["user_id"] == c.uid
    assert c.get("/api/me").json()["plan"] == "free"  # nothing paid yet

    assert _hook(cloud, _sub_event("subscription.activated", "active"), secret="wrong").status_code == 400
    assert _hook(cloud, _sub_event("subscription.activated", "active")).json()["result"] == "active"
    assert _hook(cloud, _sub_event("subscription.activated", "active")).json()["result"] == "duplicate"
    assert c.get("/api/me").json()["plan"] == "pro"
    assert c.post("/api/billing/checkout").status_code == 409
    assert _hook(cloud, {"event": "payment.captured", "payload": {}}, eid="evt_pay").json()["result"] == "ignored"

    v = c.post("/api/billing/cancel").json()
    assert posts[-1][0].endswith(f"/subscriptions/{SUB['id']}/cancel") and posts[-1][1] == {"cancel_at_cycle_end": 1}
    assert v["subscription"]["cancelAtPeriodEnd"] is True and v["plan"] == "pro"
    assert _hook(cloud, _sub_event("subscription.cancelled", "cancelled"), eid="evt_2").json()["result"] == "cancelled"
    assert c.get("/api/me").json()["plan"] == "pro"  # paid until the end of the cycle
    assert _hook(cloud, _sub_event("subscription.halted", "cancelled", end=int(time.time()) - 60), eid="evt_3").status_code == 200
    assert c.get("/api/me").json()["plan"] == "free"


def test_admin_grants_pro(cloud):
    admin, user = cloud.user("admin@example.com"), cloud.user("bala@example.com")
    assert user.post("/api/admin/grant", json={"email": "bala@example.com"}).status_code == 404
    assert admin.post("/api/admin/grant", json={"email": "bala@example.com", "until": "2099-01-01"}).json()["plan"] == "pro"
    assert user.get("/api/me").json()["plan"] == "pro"
    assert admin.post("/api/admin/grant", json={"email": "bala@example.com", "until": "2000-01-01"}).json()["plan"] == "free"
    assert admin.post("/api/admin/grant", json={"email": "bala@example.com", "until": "soon"}).status_code == 400
    assert "plans" in admin.get("/api/admin/overview").json()


def test_plan_caps_auto_apply_and_match_cadence(cloud):
    from careeros.cloud.db import now_iso
    from careeros.cloud.worker import Worker
    c = cloud.user()
    c.put("/api/d/settings/profile", json={"dailyCap": 20})
    k = cloud.client()
    k.headers["Authorization"] = "Bearer " + c.post("/api/tokens", json={"name": "pc"}).json()["key"]
    assert k.get("/api/agent/next").json()["dailyCap"] == 5
    with cloud.db.tx() as t:
        t.execute("DELETE FROM tasks")
        t.execute("DELETE FROM match_state")
        t.execute("INSERT INTO match_state(user_id, settings_hash, last_match_at, last_feed_at) VALUES (?, '', ?, ?)", (c.uid, now_iso(), now_iso()))
    w = Worker(cloud.cfg, cloud.db, cloud.app.state.mailer, worker_id="w1")
    assert w.queue_matches() == 0  # Free: already matched today
    admin = cloud.user("admin@example.com")
    admin.post("/api/admin/grant", json={"email": "asha@example.com"})
    assert w.queue_matches() >= 1 and k.get("/api/agent/next").json()["dailyCap"] == 20


def test_public_pages_and_installable_app(cloud):
    c = cloud.client()
    cloud.cfg.support_email = "help@example.com"
    for path, text in [("/pricing", "₹299"), ("/refunds", "Refunds and cancellation"), ("/contact", "help@example.com"), ("/terms", "Terms of use")]:
        r = c.get(path)
        assert r.status_code == 200 and text in r.text, path
    assert "{{" not in c.get("/privacy").text
    m = c.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.headers["content-type"].startswith("application/manifest+json") and m.json()["display"] == "standalone"
    sw = c.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"] and "caches" in sw.text
    assert c.get("/offline").status_code == 200 and "Ooops!" in c.get("/offline").text
    assert c.get("/icons/icon-192.png").content.startswith(b"\x89PNG")
    assert c.get("/icons/../app.py").status_code == 404 and c.get("/icons/nope.png").status_code == 404
    assert c.get("/apple-touch-icon.png").status_code == 200
    csp = c.get("/login").headers["content-security-policy"]
    assert "manifest-src 'self'" in csp and "worker-src 'self'" in csp
    u = cloud.user()
    page = u.get("/").text
    assert 'rel="manifest"' in page and "serviceWorker" in page and 'class="dock"' in page


def test_webhooks_out_of_order_and_older_checkout_links(cloud):
    posts = []
    _billing_on(cloud, posts)
    c = cloud.user()
    c.post("/api/billing/checkout")
    now = int(time.time())
    assert _hook(cloud, _sub_event("subscription.cancelled", "cancelled", end=now - 10, at=now), eid="e1").json()["result"] == "cancelled"
    # an older "charged" event delivered late doesn't switch Pro back on
    assert _hook(cloud, _sub_event("subscription.charged", "active", at=now - 100), eid="e2").json()["result"] == "stale"
    assert c.get("/api/me").json()["plan"] == "free"
    # paying an earlier checkout link of the same account still gives Pro
    r = _hook(cloud, _sub_event("subscription.activated", "active", sub_id="sub_OLDLINK0000001", notes={"user_id": c.uid}, at=now + 5), eid="e3")
    assert r.json()["result"] == "active" and c.get("/api/me").json()["plan"] == "pro"
    # a signed event naming an account that doesn't exist changes nothing
    assert _hook(cloud, _sub_event("subscription.activated", "active", sub_id="sub_STRANGER000001", notes={"user_id": "nope"}), eid="e4").json()["result"] == "unknown"
