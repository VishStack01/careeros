from datetime import date, datetime, timedelta, timezone

from careeros import extract


def years(text, header=""):
    return extract.extract_experience(text, header).min_years


def test_plus_and_range():
    assert years("You have 3+ years of experience building backend systems.") == 3
    assert years("We need 1-3 years of hands-on experience with Python.") == 1
    assert years("0–2 years of experience in AI.") == 0
    assert years("Minimum of two years working in ML.") == 2


def test_body_beats_header():
    # Header card said 1 year; the description asks for more. The higher wins.
    text = "Requirements:\n- 2+ years of software development, including 1+ year of GenAI work."
    assert years(text, header="1 year(s)") == 2


def test_nice_to_have_ignored():
    text = "Requirements:\n- Python\n- 1 year of experience with APIs\nNice to have:\n- 5+ years of Kubernetes experience"
    assert years(text) == 1


def test_not_experience():
    assert years("We were founded 12 years ago and serve 3 million users.") is None
    assert years("Kids aged 8 years old love our product.") is None


def test_fresher_signals():
    req = extract.extract_experience("Freshers from the 2025 batch are welcome to apply.")
    assert req.min_years is None and req.fresher_ok is True
    req = extract.extract_experience("This is not a fresher role.")
    assert req.fresher_ok is False


def test_conflicting_listing_takes_higher():
    # Real pattern: header says no experience, body says 02 Years.
    assert years("Experience: 02 Years. Strong Python.", header="No experience required") == 2


def test_title_seniority():
    assert extract.title_seniority("Senior AI Engineer") == "senior"
    assert extract.title_seniority("Software Engineer Architect - AI Agents") == "senior"
    assert extract.title_seniority("Associate AI Engineer") == "junior"
    assert extract.title_seniority("AI Engineer") == ""


def test_work_mode():
    assert extract.work_mode(structured="Remote") == "remote"
    assert extract.work_mode(location="Bengaluru (Hybrid)") == "hybrid"
    # "remote-controlled" in a description must not make a role remote.
    assert extract.work_mode(location="Hyderabad", text="We build remote-controlled robots.") == ""
    assert extract.work_mode(location="Hyderabad", text="This role is fully remote.") == "remote"


def test_remote_scope():
    assert extract.remote_scope("Remote - Worldwide", "").india_eligible is True
    assert extract.remote_scope("Remote (US only)", "").india_eligible is False
    assert extract.remote_scope("Remote", "Hiring between GMT-8 and GMT+2.").india_eligible is False
    assert extract.remote_scope("Remote", "We hire across APAC.").india_eligible is True
    assert extract.remote_scope("Remote", "Great team.").india_eligible is None


def test_salary():
    s = extract.parse_salary("CTC: ₹ 3,00,000 - 8,00,000 /year")
    assert round(s.low_lpa, 1) == 3.0 and round(s.high_lpa, 1) == 8.0
    s = extract.parse_salary("8–10 LPA")
    assert (s.low_lpa, s.high_lpa) == (8.0, 10.0)
    s = extract.parse_salary("Stipend ₹25K–₹75K /month")
    assert round(s.high_lpa, 1) == 9.0
    s = extract.parse_salary("$14k – $18k", usd_inr=88)
    assert round(s.high_lpa, 2) == round(18000 * 88 / 1e5, 2)
    assert extract.parse_salary("Competitive salary") is None


def test_misc_signals():
    assert extract.applicants("1000+ applicants") == 1000
    assert extract.closed_signal("Sorry, this job is closed.")
    assert extract.apply_by("Apply by 4 Nov' 26") == date(2026, 11, 4)
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    assert extract.posted_from_relative("Posted 3 days ago", now) == now - timedelta(days=3)
    assert extract.posted_from_relative("Reposted 2 weeks ago", now) == now - timedelta(weeks=2)
