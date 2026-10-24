"""Scores candidate bosses with the learned conditional-logit model.

For each person, P(boss = b) = exp(w . x_b) / (exp(v . z) + sum_c exp(w . x_c)),
where z are the person's "none of these" features (likely ghost, top of the company,
unreadable title...). "None" covers ghosts, the CEO, and anyone whose real boss isn't
among the candidates. Weights and department-pair priors come from model.json,
written by orgchart/evaluation/train.py.
"""

import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .data import Company
from .features import FEATURES, NONE_FEATURES, Person, candidate_pairs, none_features, read_company

MODEL_PATH = Path(__file__).with_name("model.json")


@dataclass
class Scored:
    person: Person
    options: list[tuple[str, float]]   # (boss record id, probability), best first
    p_none: float


@cache
def load_model() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError("model.json missing: run `uv run python -m orgchart.evaluation.train`")
    m = json.loads(MODEL_PATH.read_text())
    assert m["features"] == FEATURES and m["none_features"] == NONE_FEATURES, \
        "model.json was trained on a different feature set: retrain"
    m["pair_prior"] = {tuple(k.split("|")): v for k, v in m["pair_prior"].items()}
    return m


def score_company(company: Company, model: dict | None = None) -> list[Scored]:
    m = model or load_model()
    w, v = m["weights"], m["none_weights"]
    people = read_company(company)
    none_x = none_features(people)
    by_person: dict[str, list[tuple[str, float]]] = {}
    for pair in candidate_pairs(people, m["pair_prior"]):
        by_person.setdefault(pair.person, []).append((pair.boss, sum(a * b for a, b in zip(w, pair.x))))
    out = []
    for p in people:
        logits = by_person.get(p.rec.record_id, [])
        w_none = sum(a * b for a, b in zip(v, none_x[p.rec.record_id]))
        top = max([w_none] + [s for _, s in logits])
        z = math.exp(w_none - top) + sum(math.exp(s - top) for _, s in logits)
        options = sorted(((b, math.exp(s - top) / z) for b, s in logits), key=lambda t: -t[1])
        out.append(Scored(p, options, math.exp(w_none - top) / z))
    return out
