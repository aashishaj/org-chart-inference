"""Trains the boss-scoring model on the train split and writes orgchart/inference/model.json.

Lives in evaluation/ because it reads the answer key; inference only ever loads the
resulting weights. Steps:

1. Department-pair prior: P(boss's department | person's department), counted on
   train companies using the *parsed* departments (what inference will see).
2. Conditional logit: for each sampled person, softmax over their candidate bosses
   plus a "none of these" option; maximise the log-probability of the right answer.
   "None" is right for ghosts, the CEO, and people whose boss isn't a candidate,
   so the model learns when not to answer.

    uv run python -m orgchart.evaluation.train
"""

import csv
import json
import random
import time
from collections import Counter

import numpy as np
from scipy.optimize import minimize

from ..inference.data import DATA_DIR, load_companies
from ..inference.features import (FEATURES, NONE_FEATURES, TIER_A_MAX, TIER_B_MAX, TIER_C_MAX, candidate_pairs,
                                  none_features, read_company)
from ..inference.model import MODEL_PATH
from .split import companies_in

PERSON_SAMPLE = 0.4   # share of people per train company used for fitting (memory)
L2 = 1.0


def _truth() -> dict[str, dict]:
    with open(DATA_DIR / "truth" / "people.csv", newline="") as f:
        return {t["record_id"]: t for t in csv.DictReader(f)}


def train(seed: int = 0) -> dict:
    t0 = time.time()
    companies, truth = load_companies(), _truth()
    train_ids = companies_in("train")
    read = {cid: read_company(companies[cid]) for cid in train_ids}

    def same_person(a: str, b: str) -> bool:
        return truth[a]["true_person_id"] != "" and truth[a]["true_person_id"] == truth[b]["true_person_id"]

    # 1. Department-pair prior from parsed departments.
    pair_counts, totals = Counter(), Counter()
    for cid, people in read.items():
        by = {p.rec.record_id: p for p in people}
        for p in people:
            m = truth[p.rec.record_id]["expected_manager_id"]
            if m:
                pair_counts[(p.function or "?", by[m].function or "?")] += 1
                totals[p.function or "?"] += 1
    prior = {k: v / totals[k[0]] for k, v in pair_counts.items()}

    # 2. Candidate sets and labels.
    rng = random.Random(seed)
    rows, groups, labels, none_label, none_rows = [], [], [], [], []
    recall = Counter()
    for cid, people in read.items():
        sample = {p.rec.record_id for p in people if rng.random() < PERSON_SAMPLE}
        z = none_features(people)
        by_person: dict[str, list] = {}
        for pair in candidate_pairs(people, prior):
            if pair.person in sample:
                by_person.setdefault(pair.person, []).append(pair)
        for rid in sorted(sample):
            want = truth[rid]["expected_manager_id"]
            cands = by_person.get(rid, [])
            hits = [i for i, pr in enumerate(cands) if want and same_person(pr.boss, want)]
            if want:
                recall["answerable"] += 1
                recall["in_candidates"] += bool(hits)
            g = len(none_label)
            for i, pr in enumerate(cands):
                rows.append(pr.x)
                groups.append(g)
                labels.append(1.0 if hits and i == hits[0] else 0.0)
            none_label.append(0.0 if hits else 1.0)
            none_rows.append(z[rid])
    X = np.asarray(rows, dtype=np.float64)
    G = np.asarray(groups, dtype=np.int64)
    Y = np.asarray(labels)
    N = np.asarray(none_label)
    Z = np.asarray(none_rows, dtype=np.float64)
    n_groups = len(N)
    k = X.shape[1]
    print(f"train: {len(train_ids)} companies, {n_groups:,} people sampled, {len(X):,} candidate pairs; "
          f"candidate recall {recall['in_candidates'] / recall['answerable']:.1%} ({time.time() - t0:.0f}s)")

    # 3. Conditional logit with a "none" option whose utility depends on the person (Z),
    #    L2-regularised (biases excluded).
    def objective(theta):
        w, v = theta[:k], theta[k:]
        w_none = Z @ v
        s = X @ w
        top = w_none.copy()
        np.maximum.at(top, G, s)
        e = np.exp(s - top[G])
        e_none = np.exp(w_none - top)
        z = e_none.copy()
        np.add.at(z, G, e)
        logp_pos = np.zeros(n_groups)
        np.add.at(logp_pos, G, Y * (s - top[G]))
        logp_pos += N * (w_none - top)
        loss = -(logp_pos - np.log(z)).sum() + L2 * (w[1:] @ w[1:] + v[1:] @ v[1:])
        p = e / z[G]
        grad_w = X.T @ (p - Y) + 2 * L2 * np.r_[0, w[1:]]
        grad_v = Z.T @ (e_none / z - N) + 2 * L2 * np.r_[0, v[1:]]
        return loss / n_groups, np.r_[grad_w, grad_v] / n_groups

    res = minimize(objective, np.zeros(k + Z.shape[1]), jac=True, method="L-BFGS-B", options={"maxiter": 500})
    w, v = res.x[:k], res.x[k:]
    print(f"fitted in {time.time() - t0:.0f}s: loss {res.fun:.4f}, converged={res.success}")

    model = {"features": FEATURES, "weights": [round(float(a), 5) for a in w],
             "none_features": NONE_FEATURES, "none_weights": [round(float(a), 5) for a in v],
             "pair_prior": {f"{a}|{b}": round(v, 5) for (a, b), v in prior.items() if v >= 0.001},
             "tiers": [TIER_A_MAX, TIER_B_MAX, TIER_C_MAX],
             "train": {"companies": len(train_ids), "people": n_groups, "pairs": len(X),
                       "candidate_recall": recall["in_candidates"] / recall["answerable"]}}
    MODEL_PATH.write_text(json.dumps(model, indent=1) + "\n")
    return model


if __name__ == "__main__":
    m = train()
    print("\nLearned weights (positive = makes this candidate more likely the boss):")
    for name, v in sorted(zip(m["features"], m["weights"]), key=lambda t: -abs(t[1])):
        print(f"  {name:<28} {v:+.2f}")
    print("\n'None of these' weights (positive = this person more likely has no boss among candidates):")
    for name, v in zip(m["none_features"], m["none_weights"]):
        print(f"  {name:<28} {v:+.2f}")
