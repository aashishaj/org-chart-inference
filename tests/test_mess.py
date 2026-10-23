"""The title renderer must add mess without silently changing what a title means.
Any change of meaning has to be deliberate and tagged (stale, inflated, vague...),
because the tags are how we explain inference errors later."""

import copy
import dataclasses
import random

import pytest

from orgchart.generator.builder import build_company
from orgchart.generator.clues import add_clues, make_employer_pool
from orgchart.generator.mess import PROFILES, TitleContext, render_title
from orgchart.generator.templates import INDUSTRIES, SENIOR
from orgchart.generator.vocabulary import _families, load

VOCAB = load()
POOL = make_employer_pool(random.Random(0))
MEANING_TAGS = {"stale", "inflated", "vague", "creative", "fluff"}


def _render_all(profile, inflated=False, n=30, seed=1):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        industry = list(INDUSTRIES)[i % len(INDUSTRIES)]
        people = build_company(f"c{i}", industry, 300, rng)
        add_clues(people, industry, 300, rng, POOL, profile.clues)
        managers = {p.manager_id for p in people}
        for p in people:
            ctx = TitleContext(profile, VOCAB, "Acme", industry, inflated, p.id in managers)
            title, tags = render_title(p, ctx, rng)
            out.append((p, title, tags))
    return out


MESSY = _render_all(PROFILES["messy"], inflated=True)


def test_renderer_does_not_modify_person():
    rng = random.Random(3)
    people = build_company("x", "saas", 200, rng)
    before = copy.deepcopy(people)
    for p in people:
        render_title(p, TitleContext(PROFILES["messy"], VOCAB, "Acme", "saas", True, True), rng)
    assert people == before


def test_untagged_mess_never_adds_seniority():
    for p, title, tags in MESSY:
        if MEANING_TAGS & set(tags):
            continue
        extra = _families(title) - _families(p.title)
        assert not extra, f"{p.title!r} -> {title!r} gained {extra} with tags {tags}"


def test_stale_only_for_managers_and_inflation_only_when_company_inflates():
    managers = {p.manager_id for p, _, _ in MESSY}
    assert all(p.id in managers for p, _, tags in MESSY if "stale" in tags)
    assert any("stale" in tags for _, _, tags in MESSY)
    not_inflated = _render_all(PROFILES["messy"], inflated=False, n=10)
    assert not any("inflated" in tags for _, _, tags in not_inflated)


def test_ic_inflation_keeps_the_persons_own_role():
    plain = dataclasses.replace(PROFILES["messy"], vocab_variant=0, seniority_format=0, typo=0, casing=0,
                                vague=0, creative=0, fluff=0, stale=0)
    for p, title, tags in _render_all(plain, inflated=True, n=10):
        if "inflated" in tags and p.level >= SENIOR:
            core = p.title.removeprefix("Junior ").removeprefix("Graduate ")
            assert core in title, f"{p.title!r} -> {title!r}"


def test_clean_companies_are_mostly_clean():
    clean = _render_all(PROFILES["clean"], n=10)
    untouched = sum(not tags or tags == ["team"] for _, _, tags in clean) / len(clean)
    messy_untouched = sum(not tags or tags == ["team"] for _, _, tags in MESSY) / len(MESSY)
    assert untouched > 0.6 and messy_untouched < 0.35


@pytest.mark.parametrize("seed", [1, 2])
def test_deterministic(seed):
    a = [(t, g) for _, t, g in _render_all(PROFILES["medium"], n=3, seed=seed)]
    b = [(t, g) for _, t, g in _render_all(PROFILES["medium"], n=3, seed=seed)]
    assert a == b
