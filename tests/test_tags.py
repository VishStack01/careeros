

import pytest as _pytest

from careeros import tags as _tags
from careeros.scan import wanted_title


@_pytest.mark.parametrize("title,family", [
    ("Software Engineer, Backend", "Software Engineering"),
    ("SDE 1", "Software Engineering"),
    ("Frontend Developer (React)", "Software Engineering"),
    ("Machine Learning Engineer", "AI & Data"),
    ("Data Engineer", "AI & Data"),
    ("Data Analyst Intern", "AI & Data"),
    ("AI Engineer - LLM Apps", "AI & Data"),
    ("Associate Product Manager", "Product & Design"),
    ("Product Designer", "Product & Design"),
    ("Growth Marketing Manager", "Marketing & Growth"),
    ("Content Writer", "Marketing & Growth"),
    ("Sales Engineer", "Sales & Accounts"),
    ("Account Executive, Mid-Market", "Sales & Accounts"),
    ("Business Development Associate", "Sales & Accounts"),
    ("Business Analyst", "Finance & Strategy"),
    ("Founder's Office Associate", "Finance & Strategy"),
    ("Chartered Accountant", "Finance & Strategy"),
    ("Talent Acquisition Specialist", "Operations & People"),
    ("Supply Chain Operations Associate", "Operations & People"),
    ("Graduate Engineer Trainee", "Software Engineering"),
    ("Backend Engineer, Credit Cards", "Software Engineering"),
    ("Visual Merchandisers/Store Designers", "Product & Design"),
    ("Payroll Analyst", "Finance & Strategy"),
    ("Helpdesk Analyst", "Operations & People"),
    ("Test Analyst - Python+ Playwright", "Software Engineering"),
    ("Product Analyst", "AI & Data"),
    ("Market Research Associate", "Marketing & Growth"),
    ("Scientist III, Protein Biology", "AI & Data"),
    ("Solutions Engineer", "Sales & Accounts"),
    ("Chef de Partie", "Other"),
])
def test_job_family(title, family):
    assert _tags.family(title) == family


def test_scan_keeps_business_roles_but_not_unrelated_ones():
    for t in ["Growth Marketing Manager", "Account Executive", "Business Analyst", "Recruiter", "Backend Engineer", "Product Designer"]:
        assert wanted_title(t), t
    for t in ["Chef de Partie", "Delivery Driver", "Warehouse Associate"]:
        assert not wanted_title(t), t


def test_tag_includes_family():
    assert _tags.tag("Product Designer", "", {})["family"] == "Product & Design"


def test_families_in_settings_drive_the_role_gate():
    from careeros.feed import settings_from_dashboard
    from careeros.gates import gate_role
    from careeros.models import Job
    s = settings_from_dashboard({"families": ["Marketing & Growth"], "targetRoles": []})
    assert gate_role(Job(title="Growth Marketing Associate", company="X", url="u", source="test"), s).passed
    assert not gate_role(Job(title="Backend Engineer", company="X", url="u", source="test"), s).passed
    s2 = settings_from_dashboard({"families": ["Marketing & Growth"], "targetRoles": ["Community Lead"]})
    assert gate_role(Job(title="Community Lead", company="X", url="u", source="test"), s2).passed
    s3 = settings_from_dashboard({})  # no families: the built-in tech keywords still apply
    assert gate_role(Job(title="AI Engineer", company="X", url="u", source="test"), s3).passed
