"""Hacker News 'Who is hiring' posts: pay and the address each post gives for applying."""

from careeros import scan
from careeros.sources import aggregators
from careeros.sources.aggregators import apply_address


def test_apply_address_reads_emails_and_links():
    assert apply_address("Apply: jobs at acme dot io, or see our site") == "jobs@acme.io"
    assert apply_address("Email Hiring@Foo.com with your CV") == "hiring@foo.com"
    assert apply_address("Send a note to careers [at] bar [dot] ai") == "careers@bar.ai"
    assert apply_address("No address", '<a href="https://boards.greenhouse.io/x/jobs/1">Apply</a>') == "https://boards.greenhouse.io/x/jobs/1"
    assert apply_address("See https://news.ycombinator.com/item?id=1", "") == ""
    assert apply_address("We meet at the office on Fridays") == ""


def test_who_is_hiring_posts_keep_pay_and_apply_address(monkeypatch):
    html = ("Acme AI | Founding Engineer | Remote (India OK) | ₹30L - ₹45L | Full-time<p>We build agents. "
            "Apply: jobs at acme dot ai")
    def fake(url, **kw):
        if "search_by_date" in url:
            return {"hits": [{"title": "Ask HN: Who is hiring? (October 2026)", "objectID": "42"}]}
        return {"children": [{"id": 7, "text": html, "created_at": "2026-10-01T15:00:00.000Z"}, {"id": 8, "text": "Just a reply"}]}
    monkeypatch.setattr(aggregators, "get_json", fake)
    jobs = aggregators.hn_who_is_hiring()
    assert len(jobs) == 1
    j = jobs[0]
    assert (j.company, j.title, j.salary_text) == ("Acme AI", "Founding Engineer", "₹30L - ₹45L")
    assert j.raw["apply"] == "jobs@acme.ai" and j.url.endswith("id=7")
    rec = scan.to_feed(j, {"category": "remote-board"}, via="board")
    assert rec["applyTo"] == "jobs@acme.ai"
