"""Every trap the parser has fallen into, so it can't fall into it again."""

import pytest

from orgchart.inference.titles import CEO, EXEC, HEAD, JUNIOR, MGR, MID, SENIOR, SR_MGR, parse_title

CASES = [
    # (title, industry, level, function)
    # The EA's title contains "CEO"; a keyword parser crowns them head of the company.
    ("Executive Assistant to the CEO", "", MID, "executive"),
    ("EXECUTIVE ASSISTANT - CEO", "", MID, "executive"),
    # Inverted CEO titles.
    ("Director, Managing", "", CEO, "executive"),
    ("Partner, Managing", "Professional Services", CEO, "executive"),
    ("VC | Ex-Arcadia Logistics", "Education", CEO, "executive"),
    ("MD & CEO 🚀", "", CEO, "executive"),
    ("Fin Officer, Chief", "", EXEC, "finance"),
    ("Head, Information Security", "", HEAD, "security"),
    # "Manager" titles that manage no one, vs real people managers.
    ("Product Manager", "", MID, "product"),
    ("Senior Product Manager", "", SENIOR, "product"),
    ("Customer Success Manager", "", MID, "customer_success"),
    ("Senior Engineering Manager", "", SR_MGR, "engineering"),
    ("Engineering Mgr", "", MGR, "engineering"),
    # Seniority formats and teams.
    ("Software Engineer III | Core API", "", SENIOR, "engineering"),
    ("Backend Software Engineer (Junior)", "", JUNIOR, "engineering"),
    ("Grad Customer Success Manager", "", JUNIOR, "customer_success"),
    # Specialty after the comma.
    ("Engineer, Security", "", MID, "security"),
    ("Operator, Machine", "Manufacturing", MID, "production"),
    # Industry decides look-alikes.
    ("Shift Supervisor", "Mining & Resources", MGR, "mining_ops"),
    ("Shift Supervisor", "Manufacturing", MGR, "production"),
    ("Truck Driver", "Transport & Logistics", MID, "transport"),
    ("Sales Associate", "Retail", MID, "store_ops"),
    ("Retail Assistant", "Retail", MID, "store_ops"),
    # Clinical ladders and the typo fixer that once turned "Resident" into "President".
    ("Resident Medical Officer", "Healthcare", JUNIOR, "clinical"),
    ("EN", "Healthcare", JUNIOR, "clinical"),
    ("Engineering Managre", "", MGR, "engineering"),
    # "Contract" as part of a job, not a contractor flag.
    ("Contract Administrator", "Construction & Property", MID, "projects"),
]


@pytest.mark.parametrize("title,industry,level,function", CASES)
def test_known_traps(title, industry, level, function):
    p = parse_title(title, industry)
    assert (p.level, p.function) == (level, function), p


def test_flags_and_qualifiers():
    p = parse_title("Engineering Manager | Hiring!")
    assert "fluff" in p.flags and p.qualifiers == ()
    p = parse_title("Engineering Manager | Payments")
    assert p.qualifiers == ("payments",)
    assert "contractor" in parse_title("Data Engineer (Contract)").flags
    assert "contractor" in parse_title("Consultant - Data Engineer (Talent Bridge)").flags
    assert "contractor" not in parse_title("Contract Administrator").flags
    p = parse_title("A/Store Manager", "Retail")
    assert "acting" in p.flags and p.level == MGR
    assert parse_title("").flags == {"blank"}
    assert "vague" in parse_title("Team Member").flags
