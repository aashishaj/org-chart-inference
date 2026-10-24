"""Partial edges rest on ancestor probabilities; check them on a hand-built company.

    CEO
     └─ Tom (Senior EM)
          ├─ EM1
          └─ EM2
    Raj is one of EM1 / EM2's reports (50/50): too uncertain for an exact edge,
    but certain to be under Tom.
"""

from types import SimpleNamespace

import pytest

from orgchart.inference.assemble import ancestor_probabilities, assemble
from orgchart.inference.model import Scored


def _s(rid, level, options, p_none=0.0):
    return Scored(SimpleNamespace(rec=SimpleNamespace(record_id=rid), level=level), options, p_none)


COMPANY = [
    _s("ceo", 0, [], 1.0),
    _s("tom", 4, [("ceo", 1.0)]),
    _s("em1", 5, [("tom", 1.0)]),
    _s("em2", 5, [("tom", 1.0)]),
    _s("raj", 7, [("em1", 0.5), ("em2", 0.5)]),
]


def test_ancestor_probabilities_sum_over_routes():
    anc = ancestor_probabilities(COMPANY)
    assert anc["raj"]["tom"] == pytest.approx(1.0)   # under Tom whichever EM it is
    assert anc["raj"]["em1"] == pytest.approx(0.5)
    assert anc["raj"]["ceo"] == pytest.approx(1.0)


def test_uncertain_exact_becomes_partial_to_the_shared_boss():
    preds = {p.record_id: p for p in assemble(COMPANY, exact_t=0.8, partial_t=0.8)}
    assert (preds["raj"].kind, preds["raj"].manager_id) == ("partial", "tom")
    assert (preds["em1"].kind, preds["em1"].manager_id) == ("exact", "tom")
    assert preds["ceo"].kind == "none"


def test_never_claims_up_to_the_ceo():
    flat = [_s("ceo", 0, [], 1.0), _s("a", 5, [("ceo", 1.0)]), _s("b", 5, [("ceo", 1.0)]),
            _s("x", 7, [("a", 0.5), ("b", 0.5)])]
    preds = {p.record_id: p for p in assemble(flat, exact_t=0.8, partial_t=0.8)}
    assert preds["x"].kind == "none"  # only the CEO is certain, and that's useless


def test_older_echo_marks_the_earlier_holder_of_the_same_job():
    from orgchart.inference.features import older_echoes

    def person(rid, start, employer="atlassian", level=5):
        return SimpleNamespace(rec=SimpleNamespace(record_id=rid), function="engineering", level=level,
                               team="platform", employer=employer, start=start)

    people = [person("ghost", 2015 * 12), person("real", 2021 * 12), person("other", 2010 * 12, employer="canva"),
              person("ic", 2012 * 12, level=7)]
    assert older_echoes(people) == {"ghost"}
