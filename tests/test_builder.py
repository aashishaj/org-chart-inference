"""Invariants every generated true org tree must satisfy. Checked across many random
companies in every industry, because a broken answer key would make every score
we report meaningless."""

import random

import pytest

from orgchart.generator.builder import EXEC_OFFICE, build_company, sample_company_size
from orgchart.generator.templates import CEO, INDUSTRIES


def _companies(n_per_industry: int = 40):
    rng = random.Random(1234)
    for industry in INDUSTRIES:
        for i in range(n_per_industry):
            size = sample_company_size(rng)
            yield industry, size, build_company(f"{industry}{i}", industry, size, rng)


COMPANIES = list(_companies())


@pytest.mark.parametrize("industry,size,people", COMPANIES)
def test_tree_invariants(industry, size, people):
    by_id = {p.id: p for p in people}
    assert len(by_id) == len(people), "duplicate ids"

    roots = [p for p in people if p.manager_id is None]
    assert len(roots) == 1 and roots[0].level == CEO

    # Headcount: at least the target, plus a handful of execs' assistants.
    assert size <= len(people) <= size + 15

    for p in people:
        if p.manager_id is None:
            continue
        boss = by_id[p.manager_id]  # every manager exists
        if p.function != EXEC_OFFICE:  # EAs and Chiefs of Staff are allowed to sit "below" their level
            assert boss.level < p.level, f"{p.title} reports to more-junior {boss.title}"

    # No cycles: every chain reaches the CEO.
    for p in people:
        seen, cur = set(), p
        while cur.manager_id is not None:
            assert cur.id not in seen, "cycle"
            seen.add(cur.id)
            cur = by_id[cur.manager_id]


def test_sizes_in_range_and_skewed_small():
    rng = random.Random(0)
    sizes = sorted(sample_company_size(rng) for _ in range(5000))
    assert sizes[0] >= 100 and sizes[-1] <= 2000
    assert 200 <= sizes[len(sizes) // 2] <= 350  # median


def test_deterministic_for_same_seed():
    a = build_company("x", "saas", 500, random.Random(42))
    b = build_company("x", "saas", 500, random.Random(42))
    assert a == b


def test_industry_specific_reporting_appears():
    """Banks should sometimes put Security under the Chief Risk Officer, SaaS never."""
    def security_bosses(industry):
        bosses = set()
        for ind, _, people in COMPANIES:
            if ind != industry:
                continue
            by_id = {p.id: p for p in people}
            for p in people:
                if p.function == "security" and by_id[p.manager_id].function != "security":
                    bosses.add(by_id[p.manager_id].function)
        return bosses

    assert "risk" in security_bosses("financial_services")
    assert "risk" not in security_bosses("saas")
