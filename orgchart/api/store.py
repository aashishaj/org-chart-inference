"""Per-company storage for the web app.

Loading all 600 companies and the answer key at once needs over 1 GB, more than a
small server has. `split` writes each company's public records (and its slice of
the answer key) to data/by_company/<id>/, laid out like data/ itself, so the same
loaders read one company at a time. The app scores a company the first time it's
opened and keeps the most recent ones in memory.

    uv run python -m orgchart.api.store      # after generating the dataset
"""

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

from ..evaluation.scorecard import Truth, load_truth
from ..inference.assemble import ancestor_probabilities
from ..inference.data import DATA_DIR, Company, load_companies
from ..inference.features import Pair, Person, candidate_pairs, read_company
from ..inference.model import Scored, load_model, score_people

SPLIT_DIR = DATA_DIR / "by_company"
KEEP_PAIRS = 5        # candidate bosses per person kept for the "why" panel
CACHED_COMPANIES = 24


def _write(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, header)
        w.writeheader()
        w.writerows(rows)


def split(data_dir: Path = DATA_DIR, out_dir: Path = SPLIT_DIR) -> int:
    def read(path: Path) -> tuple[list[str], dict[str, list[dict]]]:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            by = defaultdict(list)
            for r in reader:
                by[r["company_id"]].append(r)
            return list(reader.fieldnames), by

    files = {"companies.csv": read(data_dir / "companies.csv"), "people.csv": read(data_dir / "people.csv")}
    if (data_dir / "truth").exists():
        for name in ("companies.csv", "people.csv", "true_tree.csv"):
            files[f"truth/{name}"] = read(data_dir / "truth" / name)
    header, companies = files["companies.csv"]
    index = []
    for cid, (row,) in companies.items():
        for name, (fields, by) in files.items():
            _write(out_dir / cid / name, fields, by.get(cid, []))
        index.append({**row, "records": len(files["people.csv"][1][cid])})
    (out_dir / "index.json").write_text(json.dumps(index))
    return len(index)


@cache
def company_index() -> list[dict]:
    index = SPLIT_DIR / "index.json"
    if not index.exists():
        raise FileNotFoundError("data/by_company missing: run `uv run python -m orgchart.api.store`")
    return json.loads(index.read_text())


@cache
def company_ids() -> frozenset[str]:
    return frozenset(c["company_id"] for c in company_index())


@dataclass
class CompanyView:
    company: Company
    people: dict[str, Person]                  # record id -> parsed record
    scored: list[Scored]
    pairs: dict[str, dict[str, Pair]]          # person -> boss -> features (top candidates only)
    anc: dict[str, dict[str, float]]


@lru_cache(maxsize=CACHED_COMPANIES)
def view(cid: str) -> CompanyView:
    company = load_companies(SPLIT_DIR / cid)[cid]
    m = load_model()
    people = read_company(company)
    all_pairs = candidate_pairs(people, m["pair_prior"])
    scored = score_people(people, all_pairs, m)
    top = {s.person.rec.record_id: {b for b, _ in s.options[:KEEP_PAIRS]} for s in scored}
    pairs: dict[str, dict[str, Pair]] = defaultdict(dict)
    for p in all_pairs:
        if p.boss in top[p.person]:
            pairs[p.person][p.boss] = p
    return CompanyView(company, {p.rec.record_id: p for p in people}, scored, dict(pairs),
                       ancestor_probabilities(scored))


@lru_cache(maxsize=CACHED_COMPANIES)
def answer_key(cid: str) -> Truth | None:
    """The hidden answer key for one company, for the app's "grade it" view only."""
    d = SPLIT_DIR / cid
    return load_truth(d, companies={cid}) if (d / "truth" / "people.csv").exists() else None


if __name__ == "__main__":
    print(f"split {split()} companies into {SPLIT_DIR}")
