"""Per-user data: isolation between accounts, the document API, files and computer keys."""

import pytest

pytest.importorskip("fastapi")

from conftest import make_pdf  # noqa: E402


def test_accounts_never_see_each_other(cloud):
    a, b = cloud.user("asha@example.com"), cloud.user("bala@example.com")
    assert a.put("/api/d/jobs/j1", json={"company": "Acme", "title": "AI Engineer", "notes": "private"}).status_code == 200
    assert b.get("/api/d/jobs/j1").status_code == 404
    assert b.get("/api/c/jobs").json()["docs"] == []
    assert b.patch("/api/d/jobs/j1", json={"notes": "hijack"}).status_code == 404
    assert b.put("/api/d/jobs/j1", json={"company": "Mine"}).status_code == 200  # b's own j1, a separate record
    b.delete("/api/d/jobs/j1")
    assert a.get("/api/d/jobs/j1").json()["data"]["notes"] == "private"
    aid = a.post("/api/assets?name=cv.pdf", content=make_pdf(), headers={"Content-Type": "application/pdf"}).json()["id"]
    assert b.get(f"/_blob/{aid}").status_code == 404 and b.delete(f"/api/assets/{aid}").status_code == 404
    assert a.get(f"/_blob/{aid}").content.startswith(b"%PDF-")
    kb = b.post("/api/tokens", json={"name": "b"}).json()["key"]
    k = cloud.client()
    k.headers["Authorization"] = f"Bearer {kb}"
    assert k.get("/api/d/jobs/j1").status_code == 404 and k.get(f"/_blob/{aid}").status_code == 404
    assert k.post("/api/agent/jobs/j1/begin").status_code == 404
    keys_a = a.get("/api/tokens").json()["keys"]
    assert keys_a == [] and b.delete(f"/api/tokens/{b.get('/api/tokens').json()['keys'][0]['id']}").status_code == 200


def test_document_api(cloud):
    c = cloud.user()
    assert c.put("/api/d/jobs/j1", json={"company": "A", "brief": {"about": "x", "stack": ["Python"]}}).json() == {"version": 1}
    assert c.patch("/api/d/jobs/j1", json={"brief": {"team": "AI"}, "stage": "approved"}).json() == {"version": 2}
    d = c.get("/api/d/jobs/j1").json()
    assert d["data"]["brief"] == {"about": "x", "stack": ["Python"], "team": "AI"} and d["version"] == 2
    assert c.patch("/api/d/jobs/j1", json={"brief": {"__delete__": True}}).status_code == 200
    assert "brief" not in c.get("/api/d/jobs/j1").json()["data"]
    assert c.patch("/api/d/jobs/j1", json={"x": 1}, headers={"If-Match": "1"}).status_code == 409
    assert c.patch("/api/d/jobs/missing", json={"x": 1}).status_code == 404
    assert c.put("/api/d/secrets/x", json={}).status_code == 404  # unknown collection
    assert c.put("/api/d/jobs/bad id!", json={}).status_code == 404
    assert c.put("/api/d/jobs/big", json={"x": "y" * (cloud.cfg.max_doc_kb * 1024 + 10)}).status_code == 413
    r = c.get("/api/c/jobs")
    tag = r.headers["etag"]
    assert c.get("/api/c/jobs", headers={"If-None-Match": tag}).status_code == 304
    c.patch("/api/d/jobs/j1", json={"notes": "changed"})
    assert c.get("/api/c/jobs", headers={"If-None-Match": tag}).status_code == 200


def test_saving_settings_queues_a_match(cloud):
    c = cloud.user()
    with cloud.db.tx() as t:
        t.execute("DELETE FROM tasks")
    c.patch("/api/d/settings/profile", json={"targetRoles": ["Product designer"]})
    with cloud.db.tx() as t:
        rows = t.all("SELECT kind, user_id FROM tasks WHERE status = 'queued'")
    assert rows == [{"kind": "match_user", "user_id": c.uid}]


def test_uploads(cloud):
    c = cloud.user()
    r = c.post("/api/assets?name=My CV.pdf", content=make_pdf("Asha Example Python FastAPI"), headers={"Content-Type": "application/pdf"})
    assert r.status_code == 201 and r.json()["url"] == f"/_blob/{r.json()['id']}"
    assert c.post("/api/assets?name=x.pdf", content=b"MZ not a pdf", headers={"Content-Type": "application/pdf"}).status_code == 415
    big = b"%PDF-1.4\n" + b"0" * (cloud.cfg.max_upload_mb * 1024 * 1024 + 10)
    assert c.post("/api/assets?name=x.pdf", content=big, headers={"Content-Type": "application/pdf"}).status_code == 413
    listing = c.get("/api/assets").json()
    assert len(listing["assets"]) == 1 and listing["usage"]["usedBytes"] > 0
    blob = c.get(f"/_blob/{r.json()['id']}")
    assert blob.headers["content-type"] == "application/pdf" and blob.headers["x-content-type-options"] == "nosniff"
    assert c.delete(f"/api/assets/{r.json()['id']}").status_code == 200 and c.get(f"/_blob/{r.json()['id']}").status_code == 404


def test_storage_quota(cloud):
    c = cloud.user()
    pdf = b"%PDF-1.4\n" + b"0" * (900 * 1024)
    codes = [c.post("/api/assets?name=x.pdf", content=pdf, headers={"Content-Type": "application/pdf"}).status_code for _ in range(3)]
    assert codes == [201, 201, 413]  # 2 MB quota in the test config


def test_computer_key_scope(cloud):
    c = cloud.user()
    key = c.post("/api/tokens", json={"name": "Work laptop"}).json()
    assert key["key"].startswith("cos_k_") and key["prefix"] == key["key"][:12]
    assert c.get("/api/tokens").json()["keys"][0]["name"] == "Work laptop"
    k = cloud.client()
    k.headers["Authorization"] = f"Bearer {key['key']}"
    assert k.get("/api/c/jobs").status_code == 200 and k.get("/api/agent/next").status_code == 200
    assert k.put("/api/d/jobs/x", json={}).status_code == 403  # keys don't write documents directly
    assert k.get("/api/tokens").status_code == 403 and k.get("/api/me/export").status_code == 403
    assert k.post("/api/me/delete", json={}).status_code == 403
    assert k.get("/api/me").json()["via"] == "key"
    c.delete(f"/api/tokens/{key['id']}")
    assert k.get("/api/c/jobs").status_code == 401
    bad = cloud.client()
    bad.headers["Authorization"] = "Bearer cos_k_notarealkey"
    assert bad.get("/api/c/jobs").status_code == 401


def test_prompts_are_served_with_the_server_address(cloud):
    c = cloud.user()
    text = c.get("/api/prompts/apply").json()["text"]
    assert "http://testserver/api/agent/next" in text and "{{SERVER}}" not in text
    assert "Career Brain" in c.get("/api/prompts/brain").json()["text"]
    assert c.get("/api/prompts/secret").status_code == 404
