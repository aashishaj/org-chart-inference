"""Company-level split: 60% train / 20% dev / 20% test, stratified by industry.

Splitting by company (never by person) means nothing about a test company's
structure leaks into training. Day-to-day iteration uses dev; test is for the
final reported numbers.
"""

import csv
import random
from collections import defaultdict
from pathlib import Path

from ..inference.data import DATA_DIR

SPLITS = ("train", "dev", "test")


def company_split(data_dir: Path = DATA_DIR, seed: int = 42) -> dict[str, str]:
    """company_id -> 'train' | 'dev' | 'test'."""
    by_industry = defaultdict(list)
    with open(data_dir / "companies.csv", newline="") as f:
        for r in csv.DictReader(f):
            by_industry[r["industry"]].append(r["company_id"])
    rng, out = random.Random(seed), {}
    for industry in sorted(by_industry):
        ids = sorted(by_industry[industry])
        rng.shuffle(ids)
        n_test = n_dev = round(len(ids) * 0.2)
        for i, cid in enumerate(ids):
            out[cid] = "test" if i < n_test else "dev" if i < n_test + n_dev else "train"
    return out


def companies_in(split: str, data_dir: Path = DATA_DIR) -> list[str]:
    return sorted(c for c, s in company_split(data_dir).items() if s == split)
