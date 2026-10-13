"""Accounts: sign-up, email verification, sign-in, password reset, sessions, export and deletion."""

import pytest

pytest.importorskip("fastapi")

PW = "correct horse battery"


def test_signup_verify_login_logout(cloud):
    c = cloud.client()
    r = c.post("/api/auth/signup", json={"email": "Asha@Example.com", "password": PW, "name": "Asha"})
    assert r.status_code == 202 and "inbox" in r.json()["message"]
    assert c.get("/api/me").status_code == 401  # not signed in until the email is confirmed
    r = c.post("/api/auth/login", json={"email": "asha@example.com", "password": PW})
    assert r.status_code == 403 and r.json()["code"] == "unverified"
    token = cloud.last_token()
    assert c.post("/api/auth/verify", json={"token": token}).status_code == 200
    me = c.get("/api/me").json()
    assert me["email"] == "asha@example.com" and me["emailVerified"] and not me["isAdmin"]
    assert c.post("/api/auth/verify", json={"token": token}).status_code == 400  # single use
    c.post("/api/auth/logout", headers={"X-CareerOS-CSRF": "1"})
    assert c.get("/api/me").status_code == 401
    c2 = cloud.client()
    assert c2.post("/api/auth/login", json={"email": "ASHA@example.com ", "password": PW}).status_code == 200
    assert c2.get("/api/me").status_code == 200
    assert c2.post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong password!"}).status_code == 401


def test_new_account_gets_default_documents(cloud):
    c = cloud.user()
    ids = {d["id"] for d in c.get("/api/c/settings").json()["docs"]}
    assert ids == {"profile"}
    assert c.get("/api/d/brain/status").json()["data"]["state"] == "waiting"


def test_signup_does_not_reveal_existing_accounts(cloud):
    cloud.user("asha@example.com")
    n = len(cloud.outbox)
    r = cloud.client().post("/api/auth/signup", json={"email": "asha@example.com", "password": "another long password", "name": "X"})
    assert r.status_code == 202 and "inbox" in r.json()["message"]  # same answer as a new account
    assert "already have" in cloud.outbox[n]["subject"]
    for email in ("nobody@example.com", "asha@example.com"):  # the same answer either way
        assert cloud.client().post("/api/auth/forgot", json={"email": email}).json()["message"].startswith("If an account")
    assert cloud.client().post("/api/auth/login", json={"email": "nobody@example.com", "password": PW}).json()["error"] == \
        cloud.client().post("/api/auth/login", json={"email": "asha@example.com", "password": "not the password"}).json()["error"]


@pytest.mark.parametrize("pw,expect", [("short", "10 characters"), ("password123", "too easy"), ("aaaaaaaaaaaa", "too easy"), ("ashaexample!!", "email")])
def test_password_rules(cloud, pw, expect):
    r = cloud.client().post("/api/auth/signup", json={"email": "ashaexample@example.com", "password": pw})
    assert r.status_code == 400 and expect in r.json()["error"]


def test_bad_email_rejected(cloud):
    assert cloud.client().post("/api/auth/signup", json={"email": "not-an-email", "password": PW}).status_code == 400


def test_login_is_rate_limited(cloud):
    cloud.user()
    c = cloud.client()
    codes = [c.post("/api/auth/login", json={"email": "asha@example.com", "password": f"wrong guess {i}"}).status_code for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[-1] == 429
    assert c.post("/api/auth/login", json={"email": "asha@example.com", "password": PW}).status_code == 429  # even the right one, for now


def test_password_reset_signs_out_everywhere(cloud):
    a = cloud.user()
    other = cloud.client()
    assert other.post("/api/auth/login", json={"email": "asha@example.com", "password": PW}).status_code == 200
    cloud.client().post("/api/auth/forgot", json={"email": "asha@example.com"})
    token = cloud.last_token("reset")
    c = cloud.client()
    assert c.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code == 400
    token = (cloud.client().post("/api/auth/forgot", json={"email": "asha@example.com"}), cloud.last_token("reset"))[1]
    assert c.post("/api/auth/reset", json={"token": token, "password": "a brand new passphrase"}).status_code == 200
    assert c.get("/api/me").status_code == 200
    assert a.get("/api/me").status_code == 401 and other.get("/api/me").status_code == 401
    assert c.post("/api/auth/reset", json={"token": token, "password": "a brand new passphrase"}).status_code == 400
    assert cloud.client().post("/api/auth/login", json={"email": "asha@example.com", "password": PW}).status_code == 401
    assert "changed" in cloud.outbox[-1]["subject"]


def test_change_password_and_logout_all(cloud):
    a = cloud.user()
    b = cloud.client()
    b.post("/api/auth/login", json={"email": "asha@example.com", "password": PW})
    assert a.post("/api/me/password", json={"current": "wrong", "new": "another passphrase"}).status_code == 400
    assert a.post("/api/me/password", json={"current": PW, "new": "another passphrase"}).status_code == 200
    assert a.get("/api/me").status_code == 200 and b.get("/api/me").status_code == 401
    assert a.post("/api/me/logout-all").status_code == 200
    assert a.get("/api/me").status_code == 401


def test_sign_in_forms_need_the_csrf_header(cloud):
    cloud.user()
    c = cloud.client()
    del c.headers["X-CareerOS-CSRF"]
    r = c.post("/api/auth/login", json={"email": "asha@example.com", "password": PW})
    assert r.status_code == 403 and r.json()["code"] == "csrf" and "cos_session" not in r.cookies
    assert c.post("/api/auth/signup", json={"email": "z@example.com", "password": PW}).status_code == 403


def test_writes_need_the_csrf_header(cloud):
    c = cloud.user()
    del c.headers["X-CareerOS-CSRF"]
    assert c.put("/api/d/jobs/j1", json={"company": "A"}).json()["code"] == "csrf"
    assert c.put("/api/d/jobs/j1", json={"company": "A"}, headers={"X-CareerOS-CSRF": "1", "Origin": "https://evil.example"}).status_code == 403
    assert c.put("/api/d/jobs/j1", json={"company": "A"}, headers={"X-CareerOS-CSRF": "1"}).status_code == 200


def test_export_and_delete_account(cloud, tmp_path):
    from conftest import make_pdf
    c = cloud.user()
    c.put("/api/d/jobs/j1", json={"company": "A", "title": "AI Engineer"})
    aid = c.post("/api/assets?name=cv.pdf", content=make_pdf(), headers={"Content-Type": "application/pdf"}).json()["id"]
    c.post("/api/tokens", json={"name": "laptop"})
    data = c.get("/api/me/export").json()
    assert data["account"]["email"] == "asha@example.com" and data["documents"]["jobs"][0]["id"] == "j1"
    assert data["files"][0]["id"] == aid and data["computerKeys"][0]["name"] == "laptop" and "password_hash" not in str(data)
    assert c.post("/api/me/delete", json={"password": PW, "confirm": "nope"}).status_code == 400
    assert c.post("/api/me/delete", json={"password": PW, "confirm": "DELETE"}).status_code == 200
    assert c.get("/api/me").status_code == 401
    with cloud.db.tx() as t:
        assert t.scalar("SELECT COUNT(*) AS n FROM users") == 0
        assert t.scalar("SELECT COUNT(*) AS n FROM docs") == 0 and t.scalar("SELECT COUNT(*) AS n FROM assets") == 0
    assert not any((cloud.cfg.upload_dir).rglob("*.pdf"))


def test_bootstrap_admin(cloud):
    admin = cloud.user("admin@example.com")
    user = cloud.user("asha@example.com")
    assert admin.get("/api/me").json()["isAdmin"]
    assert admin.get("/api/admin/overview").json()["users"] == 2
    assert user.get("/api/admin/overview").status_code == 404


def test_signup_modes(cloud):
    cloud.cfg.signup_mode, cloud.cfg.signup_allowlist = "allowlist", ["@college.edu", "friend@example.com"]
    c = cloud.client()
    assert c.post("/api/auth/signup", json={"email": "x@example.com", "password": PW}).status_code == 403
    assert c.post("/api/auth/signup", json={"email": "friend@example.com", "password": PW}).status_code == 202
    assert c.post("/api/auth/signup", json={"email": "student@college.edu", "password": PW}).status_code == 202
    cloud.cfg.signup_mode = "closed"
    assert c.post("/api/auth/signup", json={"email": "student2@college.edu", "password": PW}).status_code == 403


def test_production_refuses_unsafe_config(tmp_path):
    from careeros.cloud.app import create_app
    from careeros.cloud.config import Config
    cfg = Config(app_env="production", database_url=f"sqlite:///{tmp_path}/x.db", public_url="http://example.com")
    with pytest.raises(RuntimeError) as e:
        create_app(cfg)
    assert "PostgreSQL" in str(e.value) and "https" in str(e.value) and "SMTP_URL" in str(e.value)


def test_pages_and_headers(cloud):
    c = cloud.client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    r = c.get("/login")
    nonce = r.headers["content-security-policy"].split("'nonce-")[1].split("'")[0]
    assert f'<script nonce="{nonce}">' in r.text and r.headers["x-frame-options"] == "DENY"
    assert c.get("/privacy").status_code == 200 and "Privacy notice" in c.get("/privacy").text
    u = cloud.user()
    page = u.get("/")
    assert page.status_code == 200 and "data-act=" in page.text and 'id="demo-data"' not in page.text
    assert c.get("/api/health").json()["mode"] == "cloud"
    assert c.get("/api/ready").json()["ok"] is True
