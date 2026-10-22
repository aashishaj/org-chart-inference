"""The clue dials must do what they say: if colocate=0.8, about 80% of people sit
with their manager. Otherwise any "this clue is worth X" result would be wrong."""

import random

import pytest

from orgchart.generator.builder import build_company, sample_company_size
from orgchart.generator.clues import TODAY, TEAM_CITY, ClueConfig, add_clues, make_employer_pool
from orgchart.generator.templates import INDUSTRIES

POOL = make_employer_pool(random.Random(0))


def _dataset(cfg: ClueConfig, n: int = 120, seed: int = 5):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        industry = list(INDUSTRIES)[i % len(INDUSTRIES)]
        size = sample_company_size(rng)
        people = build_company(f"c{i}", industry, size, rng)
        facts = add_clues(people, industry, size, rng, POOL, cfg)
        out.append((industry, people, facts))
    return out


DEFAULT = _dataset(ClueConfig())


def _pairs(data):
    """(person, manager) for every reporting line."""
    for _, people, _ in data:
        by_id = {p.id: p for p in people}
        for p in people:
            if p.manager_id:
                yield p, by_id[p.manager_id]


def test_every_person_has_location_and_valid_date():
    for _, people, facts in DEFAULT:
        for p in people:
            assert p.location
            y, m = map(int, p.start_date.split("-"))
            assert facts["founded"] <= y and 1 <= m <= 12 and y + (m - 1) / 12 <= TODAY


def test_colocation_rate_matches_dial():
    # Pinned teams (stores, regions) and remote sites aren't governed by the dial.
    pairs = [(p, b) for p, b in _pairs(DEFAULT) if p.team not in TEAM_CITY and p.function not in ("mining_ops", "production")]
    rate = sum(p.location == b.location for p, b in pairs) / len(pairs)
    # Random re-placement can land in the manager's office by chance, so the rate sits a bit above 0.8.
    assert 0.80 <= rate <= 0.92


def test_joined_after_manager_rate_matches_dial():
    pairs = list(_pairs(DEFAULT))
    rate = sum(p.start_date >= b.start_date for p, b in pairs) / len(pairs)
    assert 0.80 <= rate <= 0.92


def test_followed_manager_is_rare_but_present():
    pairs = [(p, b) for p, b in _pairs(DEFAULT) if p.prev_employer and b.prev_employer]
    rate = sum(p.prev_employer == b.prev_employer for p, b in pairs) / len(pairs)
    assert 0.05 <= rate <= 0.25


def test_dials_turn_clues_off():
    off = ClueConfig(colocate=0, follow_manager=0, team_in_title_mgr=0, team_in_title_ic=0)
    data = _dataset(off, n=30)
    assert not any(p.show_team for _, people, _ in data for p in people)
    pairs = [(p, b) for p, b in _pairs(data) if p.prev_employer and b.prev_employer]
    # Only coincidences remain: common employers shared by chance.
    assert sum(p.prev_employer == b.prev_employer for p, b in pairs) / len(pairs) < 0.05


@pytest.mark.parametrize("team,city", [("QLD", "Brisbane"), ("Chadstone", "Melbourne"), ("Perth DC", "Perth")])
def test_place_pinned_teams(team, city):
    hits = [p for _, people, _ in DEFAULT for p in people if p.team == team]
    assert hits and all(p.location == city for p in hits)


def test_deterministic():
    a = _dataset(ClueConfig(), n=5, seed=9)
    b = _dataset(ClueConfig(), n=5, seed=9)
    assert a == b
