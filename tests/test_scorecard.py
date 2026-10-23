"""The scorecard decides every design choice from here on, so it gets tested with
engines whose correct score we know in advance."""

import csv
import random

import pytest

from orgchart.evaluation.scorecard import load_truth, score
from orgchart.generator.generate import generate
from orgchart.inference.data import Prediction, load_companies


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    generate(n_companies=12, seed=3, out=out)
    with open(out / "truth" / "people.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    return load_companies(out), load_truth(out), rows


def _oracle(rows, use_duplicate=False):
    dup_of = {r["duplicate_of"]: r["record_id"] for r in rows if r["duplicate_of"]}
    preds = []
    for r in rows:
        m = r["expected_manager_id"]
        if m and use_duplicate and m in dup_of:
            m = dup_of[m]  # point at the manager's duplicate record instead: still the right person
        preds.append(Prediction(r["record_id"], m or None, "exact" if m else "none", 1.0))
    return preds


def test_oracle_is_perfect(world):
    _, truth, rows = world
    m = score(_oracle(rows), truth)
    assert m["precision"] == 1.0 and m["wrong"] == 0
    assert m["exact_coverage"] == 1.0 and m["useful_coverage"] == 1.0
    assert m["attached_to_ghost"] == 0


def test_pointing_at_the_managers_duplicate_still_counts(world):
    _, truth, rows = world
    assert score(_oracle(rows, use_duplicate=True), truth)["exact_coverage"] == 1.0


def test_abstaining_everywhere_has_no_wrong_edges_and_no_coverage(world):
    _, truth, rows = world
    m = score([Prediction(r["record_id"], None, "none") for r in rows], truth)
    assert m["wrong"] == 0 and m["exact_coverage"] == 0 and m["useful_coverage"] == 0


def test_everyone_up_to_the_ceo_cannot_game_the_scorecard(world):
    # Use the *true* CEO (not the ceo_only baseline, whose CEO detection can miss
    # "Director, Managing") so this tests the scorecard alone.
    _, truth, rows = world
    ceo = {r["company_id"]: r["record_id"] for r in rows if r["kind"] == "employee" and not r["expected_manager_id"]}
    preds = [Prediction(r["record_id"], None, "none") if r["record_id"] == ceo[r["company_id"]] else
             Prediction(r["record_id"], ceo[r["company_id"]], "partial", 0.99) for r in rows]
    m = score(preds, truth)
    # True for every real employee, so precision is high...
    assert m["precision"] > 0.9
    # ...but ghosts got a manager (wrong), and "up to the CEO" only counts where the CEO
    # really is the direct manager.
    assert m["outcomes"]["false_claim"] > 0
    direct_reports_of_ceo = sum(1 for c in truth.chain.values() if len(c) == 1)
    assert m["useful_coverage"] == pytest.approx(direct_reports_of_ceo / m["answerable"])
    assert m["useful_coverage"] < 0.1


def test_random_guessing_is_heavily_penalised(world):
    companies, truth, _ = world
    rng = random.Random(0)
    preds = []
    for c in companies.values():
        ids = [r.record_id for r in c.records]
        preds += [Prediction(r.record_id, rng.choice(ids), "exact", 0.9) for r in c.records]
    m = score(preds, truth)
    assert m["precision"] < 0.05 and m["wrong_per_1k"] > 950
    assert m["ece"] > 0.8  # 90% confident, almost never right
