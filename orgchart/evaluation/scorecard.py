"""Scores an engine's predictions against the hidden answer key.

Every record ends up in one outcome:
    exact_correct    exact claim naming the right (nearest visible) manager
    exact_wrong      exact claim naming anyone else
    partial_correct  "reports up to X" where X really is above them (gap = levels above the manager)
    partial_wrong    "reports up to X" where X is not above them
    false_claim      a manager claimed for a record that has none (the CEO, a ghost)
    abstain          no claim on a record that has a manager
    correct_none     no claim on a record that has no manager

Headline numbers: precision of claims, wrong edges per 1,000 records, exact coverage
and *useful* coverage: exact claims plus partial claims at most USEFUL_GAP levels
above the real manager. "Reports up to the CEO" is never a useful partial claim
(everyone does), so vague claims can't score well even in small, flat companies.
"""

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..inference.data import DATA_DIR, Prediction

USEFUL_GAP = 1
CONFIDENCE_BINS = 10


@dataclass
class Truth:
    kind: dict[str, str] = field(default_factory=dict)              # record -> employee | ghost | duplicate
    chain: dict[str, list[frozenset[str]]] = field(default_factory=dict)  # visible bosses, nearest first
    company: dict[str, str] = field(default_factory=dict)
    mess_level: dict[str, str] = field(default_factory=dict)        # company -> clean | medium | messy
    tags: dict[str, list[str]] = field(default_factory=dict)


def load_truth(data_dir: Path = DATA_DIR, companies: set[str] | None = None) -> Truth:
    t = Truth()
    tdir = data_dir / "truth"
    with open(tdir / "companies.csv", newline="") as f:
        t.mess_level = {r["company_id"]: r["mess_level"] for r in csv.DictReader(f)}
    manager, person_records = {}, defaultdict(set)
    rows = []
    with open(tdir / "people.csv", newline="") as f:
        for r in csv.DictReader(f):
            if companies is not None and r["company_id"] not in companies:
                continue
            rows.append(r)
            if r["true_person_id"]:
                person_records[r["true_person_id"]].add(r["record_id"])
    with open(tdir / "true_tree.csv", newline="") as f:
        for r in csv.DictReader(f):
            if companies is None or r["company_id"] in companies:
                manager[r["person_id"]] = r["manager_person_id"] or None

    chains: dict[str, list[frozenset[str]]] = {}

    def chain_of(pid: str) -> list[frozenset[str]]:
        if pid not in chains:
            out, cur = [], manager.get(pid)
            while cur:
                if cur in person_records:
                    out.append(frozenset(person_records[cur]))
                cur = manager.get(cur)
            chains[pid] = out
        return chains[pid]

    for r in rows:
        rid = r["record_id"]
        t.kind[rid], t.company[rid] = r["kind"], r["company_id"]
        t.tags[rid] = [x for x in r["mess_tags"].split(";") if x]
        t.chain[rid] = chain_of(r["true_person_id"]) if r["true_person_id"] else []
        if r["expected_manager_id"]:
            assert r["expected_manager_id"] in t.chain[rid][0], "answer key and tree disagree"
    return t


def _outcome(p: Prediction | None, chain: list[frozenset[str]]) -> tuple[str, int | None]:
    claimed = p is not None and p.kind in ("exact", "partial") and p.manager_id
    if not chain:
        return ("false_claim", None) if claimed else ("correct_none", None)
    if not claimed:
        return "abstain", None
    gap = next((i for i, recs in enumerate(chain) if p.manager_id in recs), None)
    if p.kind == "exact":
        return ("exact_correct", 0) if gap == 0 else ("exact_wrong", None)
    if gap is None:
        return "partial_wrong", None
    return ("partial_correct", gap) if gap == 0 or gap < len(chain) - 1 else ("partial_to_top", gap)


def _useful(outcome: str, gap: int | None) -> bool:
    return outcome == "exact_correct" or (outcome == "partial_correct" and gap <= USEFUL_GAP)


WRONG = {"exact_wrong", "partial_wrong", "false_claim"}


def score(predictions: list[Prediction], truth: Truth) -> dict:
    preds = {p.record_id: p for p in predictions}
    outcomes, gaps, calib = Counter(), Counter(), []
    by_level = defaultdict(Counter)
    ghosts = {r for r, k in truth.kind.items() if k == "ghost"}
    attached_to_ghost = 0
    for rid, chain in truth.chain.items():
        p = preds.get(rid)
        o, gap = _outcome(p, chain)
        outcomes[o] += 1
        level = truth.mess_level[truth.company[rid]]
        by_level[level][o] += 1
        by_level[level]["answerable"] += bool(chain)
        if o in ("partial_correct", "partial_to_top"):
            gaps[gap] += 1
        by_level[level]["useful"] += _useful(o, gap)
        if o in WRONG or o in ("exact_correct", "partial_correct", "partial_to_top"):
            calib.append((p.confidence, o not in WRONG))
        if p is not None and p.manager_id in ghosts and p.kind != "none":
            attached_to_ghost += 1

    n = len(truth.chain)
    answerable = sum(1 for c in truth.chain.values() if c)
    claims = len(calib)
    wrong = sum(outcomes[o] for o in WRONG)
    exact_claims = outcomes["exact_correct"] + outcomes["exact_wrong"]
    useful = sum(c["useful"] for c in by_level.values())

    bins = [[] for _ in range(CONFIDENCE_BINS)]
    for conf, ok in calib:
        bins[min(int(conf * CONFIDENCE_BINS), CONFIDENCE_BINS - 1)].append(ok)
    reliability = [{"bin": f"{i / CONFIDENCE_BINS:.1f}-{(i + 1) / CONFIDENCE_BINS:.1f}", "claims": len(b),
                    "accuracy": sum(b) / len(b) if b else None} for i, b in enumerate(bins)]
    ece = sum(len(b) / claims * abs(sum(b) / len(b) - (i + 0.5) / CONFIDENCE_BINS)
              for i, b in enumerate(bins) if b) if claims else 0.0

    def level_summary(c: Counter) -> dict:
        lc = sum(c[o] for o in ("exact_correct", "partial_correct", "partial_to_top")) + sum(c[o] for o in WRONG)
        lw = sum(c[o] for o in WRONG)
        return {"precision": 1 - lw / lc if lc else None,
                "exact_coverage": c["exact_correct"] / c["answerable"] if c["answerable"] else None,
                "useful_coverage": c["useful"] / c["answerable"] if c["answerable"] else None}

    return {
        "records": n, "answerable": answerable, "claims": claims, "wrong": wrong,
        "precision": 1 - wrong / claims if claims else None,
        "exact_precision": outcomes["exact_correct"] / exact_claims if exact_claims else None,
        "wrong_per_1k": 1000 * wrong / n if n else 0.0,
        "exact_coverage": outcomes["exact_correct"] / answerable if answerable else 0.0,
        "useful_coverage": useful / answerable if answerable else 0.0,
        "mean_partial_gap": (sum(g * v for g, v in gaps.items()) / sum(gaps.values())) if gaps else None,
        "partial_gaps": {str(g): v for g, v in sorted(gaps.items())},
        "attached_to_ghost": attached_to_ghost,
        "ece": ece,
        "outcomes": dict(outcomes),
        "by_mess_level": {lvl: level_summary(by_level[lvl]) for lvl in ("clean", "medium", "messy") if lvl in by_level},
        "reliability": reliability,
    }


HEADLINE = [("precision", "Precision of claims", "pct"), ("wrong_per_1k", "Wrong edges per 1,000 records", "num"),
            ("exact_coverage", "Exact coverage", "pct"), ("useful_coverage", "Useful coverage (exact + partial ≤1 up)", "pct"),
            ("mean_partial_gap", "Mean partial gap (levels above manager)", "num"),
            ("attached_to_ghost", "Records attached to a ghost", "int"), ("ece", "Calibration error (ECE)", "pct")]


def _fmt(v, kind):
    if v is None:
        return "-"
    return {"pct": f"{v:.1%}", "num": f"{v:.2f}", "int": f"{v:,}"}[kind]


def format_report(name: str, split: str, m: dict, previous: dict | None = None) -> str:
    lines = [f"\n=== {name} on {split} ({m['records']:,} records, {m['answerable']:,} with a manager) ==="]
    for key, label, kind in HEADLINE:
        delta = ""
        if previous and previous.get(key) is not None and m.get(key) is not None:
            d = m[key] - previous[key]
            if abs(d) > 1e-9:
                delta = f"   ({'+' if d > 0 else ''}{_fmt(d, kind) if kind != 'int' else f'{d:,}'} vs last run)"
        lines.append(f"  {label:<42} {_fmt(m.get(key), kind):>8}{delta}")
    lines.append("  By mess level:" + "".join(
        f"  {lvl} P {_fmt(s['precision'], 'pct')} / exact {_fmt(s['exact_coverage'], 'pct')} / useful "
        f"{_fmt(s['useful_coverage'], 'pct')} |" for lvl, s in m["by_mess_level"].items()))
    rel = [r for r in m["reliability"] if r["claims"]]
    if rel:
        lines.append("  Reliability (confidence -> actual): " + ", ".join(
            f"{r['bin']}: {r['accuracy']:.0%} (n={r['claims']:,})" for r in rel))
    return "\n".join(lines)
