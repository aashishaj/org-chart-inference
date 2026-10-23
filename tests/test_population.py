"""The answer key after population mess. Every correct answer must be a visible
record that really is above the person in the true tree; ghosts must never be
anyone's manager."""

import random

import pytest

from orgchart.generator.builder import build_company, sample_company_size
from orgchart.generator.clues import add_clues, make_employer_pool
from orgchart.generator.fields import NameMaker
from orgchart.generator.population import POP_RATES, build_population
from orgchart.generator.templates import CEO, INDUSTRIES

POOL = make_employer_pool(random.Random(0))


def _companies(level: str, n: int = 40, seed: int = 6):
    rng, names = random.Random(seed), NameMaker(seed)
    for i in range(n):
        industry = list(INDUSTRIES)[i % len(INDUSTRIES)]
        size = sample_company_size(rng)
        people = build_company(f"c{i}", industry, size, rng)
        add_clues(people, industry, size, rng, POOL)
        yield people, *build_population(people, level, rng, names.make)


MESSY = list(_companies("messy"))


@pytest.mark.parametrize("people,records,truth", MESSY[::4])
def test_expected_manager_is_a_visible_true_ancestor(people, records, truth):
    by_id = {p.id: p for p in people}
    keys = {r.key for r in records}

    def ancestors(pid):
        out, cur = [], by_id[pid].manager_id
        while cur:
            out.append(cur)
            cur = by_id[cur].manager_id
        return out

    for t in truth.values():
        if t.kind == "ghost" or t.true_manager_id is None:
            continue
        assert t.expected_manager in keys
        chain = ancestors(t.true_person_id)
        assert t.expected_manager == chain[t.hops], "expected = first visible ancestor, hops levels up"
        assert all(a not in keys for a in chain[: t.hops]), "skipped bosses must be invisible"


def test_ghosts_never_manage_and_have_no_manager():
    for _, _, truth in MESSY:
        ghosts = {k for k, t in truth.items() if t.kind == "ghost"}
        assert ghosts
        assert all(truth[g].expected_manager is None for g in ghosts)
        assert not any(t.expected_manager in ghosts for t in truth.values())


def test_ghost_started_before_the_role_it_copies():
    for people, records, _ in MESSY:
        by_title = {}
        for p in people:
            by_title.setdefault((p.function, p.title, p.team), []).append(p.start_date)
        for r in records:
            if r.kind == "ghost":
                assert r.person.start_date < max(by_title[(r.person.function, r.person.title, r.person.team)])


def test_duplicates_share_the_original_answer():
    for _, _, truth in MESSY:
        for t in truth.values():
            if t.kind == "duplicate":
                orig = truth[t.duplicate_of]
                assert (t.expected_manager, t.true_person_id) == (orig.expected_manager, orig.true_person_id)


def test_ceo_always_visible_and_rates_scale():
    for people, records, _ in MESSY:
        ceo = next(p for p in people if p.level == CEO)
        assert any(r.key == ceo.id for r in records)

    def missing_rate(data):
        staff = sum(len(p) for p, _, _ in data)
        seen = sum(sum(t.kind == "employee" for t in tr.values()) for _, _, tr in data)
        return 1 - seen / staff

    clean = list(_companies("clean", n=20))
    assert missing_rate(clean) < missing_rate(MESSY)
    assert abs(missing_rate(MESSY) - POP_RATES["messy"].missing) < 0.03
