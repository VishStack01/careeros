"""Company logos: a logo only for a company whose own website the evidence names, never a guess."""

import io
import json
import struct
import zlib

from careeros import logos


def png(width: int) -> bytes:
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(width))
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, width, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def test_registrable_domains():
    assert logos.registrable("careers.airbnb.com") == "airbnb.com"
    assert logos.registrable("jobs.tcs.co.in") == "tcs.co.in"
    assert logos.registrable("localhost") == ""


def test_names_match_their_own_domains_only():
    assert logos.matches("Sarvam AI", "sarvam.ai")
    assert logos.matches("HG Insights", "hginsights.com")
    assert logos.matches("Motive", "gomotive.com")
    assert logos.matches("Lingo.dev", "lingo.dev")
    assert not logos.matches("Spenmo", "summitglobal.com")
    assert not logos.matches("Acme", "greenhouse.io")


def test_domain_comes_from_evidence():
    # The company's own careers host
    assert logos.domain_for("Airbnb", ["https://careers.airbnb.com/positions/1"], []) == "airbnb.com"
    # A hiring system's host is never the company's site; the posting's own link or email is
    assert logos.domain_for("Kyndryl", ["https://kyndryl.wd5.myworkdayjobs.com/x"], ["Apply at careers@kyndryl.com. See www.linkedin.com/company/kyndryl"]) == "kyndryl.com"
    # A domain that names another company isn't used
    assert logos.domain_for("Acme", ["https://boards.greenhouse.io/acme/jobs/1"], ["We partner with stripe.com and openai.com"]) == ""
    # The website on record wins
    assert logos.domain_for("Spenmo", [], [], website="https://summitglobal.com/") == "summitglobal.com"


def test_guesses_are_checked_against_the_site(tmp_path):
    seen = []

    def get(url):
        seen.append(url)
        if url == "https://kyndryl.com/":
            return 200, "text/html", b"<html><title>Kyndryl | Infrastructure services</title></html>"
        if url == "https://acmerobotics.com/":
            return 200, "text/html", b"<title>Parked domain for sale</title>"
        if "s2/favicons" in url:
            return 200, "image/png", png(64)
        return 404, "", b""
    mapping = {"kyndryl": "?" + ",".join(logos.guesses("Kyndryl")) + "|Kyndryl",
               "acme-robotics": "?" + ",".join(logos.guesses("Acme Robotics")) + "|Acme Robotics",
               "airbnb": "airbnb.com"}
    res = logos.update(tmp_path, mapping, get=get, log=lambda *_: None)
    assert res["withLogo"] == 2
    files = logos.for_site(tmp_path)
    assert set(files) == {"kyndryl", "airbnb"}  # the parked domain didn't name the company
    # A second run within the refresh window fetches nothing
    seen.clear()
    logos.update(tmp_path, mapping, get=get, log=lambda *_: None)
    assert seen == []


def test_tiny_or_broken_icons_are_skipped():
    calls = iter([(200, "image/png", png(16)), (200, "text/html", b"<html>not an image</html>"), (404, "", b"")])
    assert logos.fetch_icon("tiny.com", get=lambda url: next(calls)) is None
    assert logos.fetch_icon("ok.com", get=lambda url: (200, "image/png", png(96)))[1] == "png"


def test_site_publishes_logos(tmp_path):
    from conftest import feed_record, write_feed
    from careeros import site
    feed = tmp_path / "feed"
    write_feed(feed, [feed_record(1, company="Company 1"), feed_record(2, company="Company 2")])
    cache = tmp_path / "cache"
    logos.update(cache, {"company-1": "company1.com"}, get=lambda url: (200, "image/png", png(64)), log=lambda *_: None)
    site.build(feed, tmp_path / "out", log=lambda *_: None, website=None, logos_dir=cache)
    jobs = json.loads((tmp_path / "out" / "data" / "jobs.json").read_text())["jobs"]
    by = {j["c"]: j for j in jobs}
    assert by["Company 1"]["lo"].startswith("logos/") and (tmp_path / "out" / by["Company 1"]["lo"]).exists()
    assert "lo" not in by["Company 2"]
