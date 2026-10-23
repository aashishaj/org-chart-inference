"""Field mess must stay recoverable: a messy location or date still decodes to the
true value. Only tagged mess (blank, remote, wrong department) may lose information."""

import random
import re

from orgchart.generator.builder import build_company
from orgchart.generator.clues import add_clues, make_employer_pool
from orgchart.generator.fields import (DEPT_SYNONYMS, FIELD_RATES, MONTHS, NameMaker, dept_label, department_owners,
                                       parse_location, render_fields)
from orgchart.generator.templates import INDUSTRIES

POOL = make_employer_pool(random.Random(0))


def _rows(level: str, n: int = 20, seed: int = 4):
    rng, names = random.Random(seed), NameMaker(seed)
    out = []
    for i in range(n):
        industry = list(INDUSTRIES)[i % len(INDUSTRIES)]
        people = build_company(f"c{i}", industry, 300, rng)
        add_clues(people, industry, 300, rng, POOL)
        owners = department_owners(people)
        for p in people:
            rec, tags = render_fields(p, p.title, level, owners, names.make(rng), rng)
            out.append((p, rec, tags, owners))
    return out


MESSY = _rows("messy")


def _parse_date(s: str) -> tuple[int, int | None]:
    if re.fullmatch(r"\d{4}", s):
        return int(s), None
    if m := re.fullmatch(r"(\d{4})[-/](\d{2})", s):
        return int(m[1]), int(m[2])
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", s):
        return int(m[2]), int(m[1])
    month, year = s.split(" ")
    return int(year), [x[: len(month)] for x in MONTHS].index(month) + 1


def test_messy_locations_decode_to_the_true_city():
    for p, rec, tags, _ in MESSY:
        if rec["location"] and "remote" not in tags:
            assert parse_location(rec["location"]) == p.location, (rec["location"], p.location)


def test_messy_dates_decode_to_the_true_month():
    for p, rec, tags, _ in MESSY:
        if not rec["start_date"]:
            continue
        year, month = _parse_date(rec["start_date"])
        ty, tm = map(int, p.start_date.split("-"))
        assert year == ty and (month is None or month == tm), (rec["start_date"], p.start_date)


def test_department_is_true_leaked_or_tagged_wrong():
    for p, rec, tags, owners in MESSY:
        d = rec["department"]
        if not d or "dept_wrong" in tags:
            continue
        fn = owners[p.function] if "dept_leak" in tags else p.function
        assert d == dept_label(fn) or d in DEPT_SYNONYMS[fn], (p.function, d, tags)


def test_rates_scale_with_mess_level():
    clean = _rows("clean", n=10)

    def rate(rows, tag):
        return sum(tag in t for _, _, t, _ in rows) / len(rows)

    for tag in ["dept_missing", "loc_missing", "date_missing", "title_missing"]:
        assert rate(clean, tag) < rate(MESSY, tag)
    assert abs(rate(MESSY, "dept_missing") - FIELD_RATES["messy"].dept_missing) < 0.03


def test_names_are_diverse_and_deterministic():
    a, b = NameMaker(1), NameMaker(1)
    ra, rb = random.Random(1), random.Random(1)
    names_a = [a.make(ra) for _ in range(300)]
    assert names_a == [b.make(rb) for _ in range(300)]
    assert len({last for _, last in names_a}) > 150
