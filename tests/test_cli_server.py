import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from careeros import cli
from careeros.server import make_handler
from careeros.store import Store

ROOT = Path(__file__).parents[1]


def test_evaluate_command(tmp_path, capsys):
    posting = tmp_path / "p.txt"
    posting.write_text("We hire freshers. Requirements: 0-1 years of experience with Python. This role is fully remote within India.")
    cli.main(["--db", str(tmp_path / "t.db"), "evaluate", "--company", "Demo Co", "--title", "Junior AI Engineer",
              "--location", "India", "--mode", "remote", "--text-file", str(posting),
              "--settings", str(ROOT / "config" / "settings.example.toml"), "--save"])
    out = json.loads(capsys.readouterr().out)
    assert out["kept"] and out["region"] == "remote-india" and out["saved"]["status"] == "new"


def test_claims_check_command(tmp_path, capsys):
    resume = tmp_path / "r.json"
    resume.write_text(json.dumps({"bullets": [{"text": "Cut invoice entry from 30 to 4 hours a month.", "refs": ["ach-invoices"]}]}))
    try:
        cli.main(["claims-check", str(resume), "--brain", str(ROOT / "brain" / "brain.example.json")])
    except SystemExit as e:
        assert e.code == 0
    assert "OK to send" in capsys.readouterr().out


def test_server_api(tmp_path):
    store = Store(tmp_path / "t.db")
    store.set("jobs", "demo", {"title": "AI Engineer", "stage": "found"})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, ROOT / "dashboard"))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert json.load(urllib.request.urlopen(base + "/api/health"))["ok"]
        docs = json.load(urllib.request.urlopen(base + "/api/c/jobs"))["docs"]
        assert docs[0]["id"] == "demo"
        req = urllib.request.Request(base + "/api/d/jobs/demo", data=json.dumps({"stage": "approved"}).encode(), method="PATCH")
        urllib.request.urlopen(req)
        assert store.get("jobs", "demo")["data"]["stage"] == "approved"
        # Paths outside the dashboard folder are refused.
        try:
            urllib.request.urlopen(base + "/../pyproject.toml")
            raise AssertionError("served a file outside the dashboard")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        httpd.shutdown()
