"""Public data only: the files any data provider would have, plus the prediction
format every inference engine returns.

Nothing in orgchart/inference may read the hidden answer key or import
orgchart.generator; tests/test_no_peeking.py enforces it.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True)
class Record:
    record_id: str
    company_id: str
    name: str
    title: str
    department: str
    location: str
    start_date: str
    prev_employer: str


@dataclass
class Company:
    company_id: str
    name: str
    industry: str
    headcount_band: str
    hq: str
    records: list[Record] = field(default_factory=list)


@dataclass(frozen=True)
class Prediction:
    """One answer per record.

    kind "exact":   manager_id is this person's direct (nearest visible) manager.
    kind "partial": manager_id is somewhere above this person ("reports up to").
    kind "none":    abstain, or this record has no manager (the CEO, a ghost).
    """
    record_id: str
    manager_id: str | None
    kind: str
    confidence: float = 0.0
    reason: str = ""


def load_companies(data_dir: Path = DATA_DIR) -> dict[str, Company]:
    with open(data_dir / "companies.csv", newline="") as f:
        companies = {r["company_id"]: Company(**r) for r in csv.DictReader(f)}
    with open(data_dir / "people.csv", newline="") as f:
        for r in csv.DictReader(f):
            companies[r["company_id"]].records.append(Record(**r))
    return companies
