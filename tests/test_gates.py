from datetime import datetime, timedelta, timezone

from careeros.gates import evaluate
from careeros.models import Job
from careeros.settings import Settings

NOW = datetime(2026, 10, 9, 6, 0, tzinfo=timezone.utc)
S = Settings()  # defaults: <=1 year, 25 days, 7 LPA floor, south India any / rest remote / abroad remote


def job(**kw):
    base = dict(company="Example Labs", title="AI Engineer", url="https://example.com/j/1", source="test",
                posted_at=(NOW - timedelta(days=2)).isoformat(), description="1 year of experience with Python and LLM APIs.")
    base.update(kw)
    return Job(**base)


def failed(d):
    return [c.gate for c in d.checks if not c.passed]


def test_south_india_onsite_kept():
    d = evaluate(job(location="Chennai", work_mode="onsite"), S, NOW)
    assert d.kept and d.region == "south-india"


def test_rest_of_india_onsite_skipped():
    d = evaluate(job(location="Pune", work_mode="onsite"), S, NOW)
    assert not d.kept and failed(d) == ["Location"]


def test_rest_of_india_remote_kept():
    d = evaluate(job(location="Pune, India", work_mode="remote"), S, NOW)
    assert d.kept and d.region == "remote-india"


def test_multi_city_with_bengaluru_kept():
    d = evaluate(job(location="Bengaluru, Delhi, Gurgaon or Mumbai"), S, NOW)
    assert d.kept and d.region == "south-india"


def test_remote_worldwide_is_top_priority_region():
    d = evaluate(job(location="Remote - Anywhere", work_mode="remote"), S, NOW)
    assert d.kept and d.region == "remote-global"


def test_remote_us_only_skipped():
    d = evaluate(job(location="Remote (US only)", work_mode="remote"), S, NOW)
    assert not d.kept and "Location" in failed(d)


def test_experience_gate_uses_description():
    d = evaluate(job(description="You bring 2+ years of software development experience."), S, NOW)
    assert not d.kept and failed(d) == ["Experience"]
    exp = next(c for c in d.checks if c.gate == "Experience")
    assert "2+ years" in exp.quote


def test_senior_title_skipped():
    d = evaluate(job(title="Senior AI Engineer"), S, NOW)
    assert "Seniority" in failed(d)


def test_old_posting_skipped_and_fresh_is_priority():
    old = evaluate(job(posted_at=(NOW - timedelta(days=30)).isoformat()), S, NOW)
    assert "Posted" in failed(old)
    fresh = evaluate(job(location="Hyderabad", posted_at=(NOW - timedelta(hours=10)).isoformat()), S, NOW)
    assert fresh.kept and fresh.priority


def test_pay_floor_uses_top_of_range():
    low = evaluate(job(location="Bengaluru", salary_text="₹ 3,60,000 - 6,00,000 /year"), S, NOW)
    assert failed(low) == ["Pay"]
    ok = evaluate(job(location="Bengaluru", salary_text="₹ 3,00,000 - 8,00,000 /year"), S, NOW)
    assert ok.kept


def test_closed_and_deadline():
    d = evaluate(job(location="Bengaluru", description="This job is closed."), S, NOW)
    assert "Open" in failed(d)
    d = evaluate(job(location="Bengaluru", apply_by="2026-10-01"), S, NOW)
    assert "Open" in failed(d)


def test_non_target_role_skipped():
    d = evaluate(job(title="Field Sales Executive", location="Bengaluru"), S, NOW)
    assert "Role" in failed(d)


def test_role_keywords_match_plurals():
    from careeros.gates import gate_role
    from careeros.models import Job
    from careeros.settings import Settings
    assert gate_role(Job(company="X", title="Full-stack Engineer - Creative Agents", url="", source="test"), Settings()).passed
    assert not gate_role(Job(company="X", title="Account Executive", url="", source="test"), Settings()).passed


def test_remote_country_in_title():
    from careeros.gates import gate_location
    from careeros.models import Job
    from careeros.settings import Settings
    for title in ("Product Engineer (Remote/US)", "QA Analyst (Mexico, Remote)", "Product Engineers in Canada (Remote)"):
        c, region = gate_location(Job(company="X", title=title, url="", source="t", location="Remote", work_mode="remote"), Settings())
        assert not c.passed and region == "", title
    c, region = gate_location(Job(company="X", title="Backend Engineer (Remote, India)", url="", source="t", location="Remote", work_mode="remote"), Settings())
    assert c.passed and region == "remote-india"
