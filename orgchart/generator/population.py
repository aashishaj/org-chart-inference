"""The mess layer, part 3: who is in the data at all.

- Missing employees: real staff the data provider never saw. Their reports' correct
  answer becomes the nearest *visible* boss (a skip-level line, hops recorded).
- Ghosts: people who left but are still listed. Same title and team as a real role,
  earlier start date (they were replaced). Correct answer: no manager, and never
  anyone's manager.
- Duplicates: the same person twice. Same correct manager as the original.
- Contractors: real team members whose titles say "contract" / "via <agency>".

Produces observed records (what gets rendered into people.csv) and the truth rows
(the answer key). Record keys here are internal; the dataset writer replaces them
with shuffled opaque ids.
"""

import dataclasses
import random
from dataclasses import dataclass, field

from .builder import Person
from .templates import CEO, EXEC, MGR, SENIOR


@dataclass(frozen=True)
class PopulationRates:
    missing: float      # share of real staff not in the data
    ghosts: float       # ex-employees still listed, as a share of company size
    duplicates: float   # share of visible people listed twice
    contractors: float  # share of visible ICs flagged as contractors


POP_RATES = {
    "clean": PopulationRates(missing=.05, ghosts=.02, duplicates=.005, contractors=.02),
    "medium": PopulationRates(missing=.10, ghosts=.04, duplicates=.015, contractors=.04),
    "messy": PopulationRates(missing=.15, ghosts=.07, duplicates=.03, contractors=.06),
}

AGENCIES = ["Talent Bridge", "Peoplefirst Recruitment", "Apex Contracting", "Southern Talent", "Harbour Staffing",
            "Bluechip Resourcing", "Clarity Recruitment", "Northgate Talent"]
CONTRACT_FORMATS = ["{t} (Contract)", "Contractor - {t}", "{t} - Contract", "{t} (via {agency})",
                    "Contract {t}", "{t} | Contractor", "{t} (Fixed Term)", "Consultant - {t} ({agency})"]
NICKNAMES = {"Jennifer": "Jen", "Michael": "Mike", "Christopher": "Chris", "Elizabeth": "Liz", "William": "Will",
             "Robert": "Rob", "Katherine": "Kate", "Matthew": "Matt", "Daniel": "Dan", "Alexander": "Alex",
             "Rebecca": "Bec", "Samantha": "Sam", "Benjamin": "Ben", "Nicholas": "Nick", "Thomas": "Tom",
             "Jessica": "Jess", "Stephanie": "Steph", "Andrew": "Andy", "James": "Jim", "Margaret": "Maggie"}


@dataclass
class ObservedRecord:
    key: str
    person: Person                  # what gets rendered (a ghost is a synthetic Person)
    name: tuple[str, str]
    kind: str                       # employee | ghost | duplicate
    contractor: bool = False


@dataclass
class TruthRow:
    key: str
    kind: str
    true_person_id: str | None      # None for ghosts
    true_manager_id: str | None     # the real manager (person id), may be invisible
    expected_manager: str | None    # record key of the nearest visible boss: the correct answer
    hops: int = 0                   # 0 = direct manager is visible; 1+ = skip-level
    duplicate_of: str | None = None
    tags: list[str] = field(default_factory=list)


def contractor_title(title: str, rng: random.Random) -> str:
    return rng.choice(CONTRACT_FORMATS).format(t=title or "Contractor", agency=rng.choice(AGENCIES))


def _drop_weight(p: Person) -> float:
    """Executives are the most visible people in any company; ICs the least."""
    if p.level == CEO:
        return 0.0
    if p.level <= EXEC:
        return 0.3
    return 0.8 if p.level <= MGR else 1.2


def _earlier(iso: str, floor: str, rng: random.Random) -> str:
    """A start date before `iso` (the ghost's replacement started later)."""
    y, m = map(int, iso.split("-"))
    fy, fm = map(int, floor.split("-"))
    hi, lo = y * 12 + m - 2, fy * 12 + fm - 1
    t = rng.randint(min(lo, hi), hi) if hi > lo else hi
    return f"{t // 12}-{t % 12 + 1:02d}"


def _name_variant(name: tuple[str, str], rng: random.Random) -> tuple[str, str]:
    first, last = name
    if first in NICKNAMES and rng.random() < 0.5:
        return NICKNAMES[first], last
    if rng.random() < 0.5:
        return first, f"{last}-{rng.choice(['Lee', 'Smith', 'Jones', 'Brown', 'Ng', 'Taylor'])}"  # married name
    return first, last


def build_population(people: list[Person], profile_name: str, rng: random.Random,
                     make_name) -> tuple[list[ObservedRecord], dict[str, TruthRow]]:
    rates = POP_RATES[profile_name]
    by_id = {p.id: p for p in people}
    managers = {p.manager_id for p in people if p.manager_id}

    # 1. Missing employees.
    avg = sum(_drop_weight(p) for p in people) / len(people)
    visible = {p.id for p in people if rng.random() >= rates.missing * _drop_weight(p) / avg}

    names = {p.id: make_name(rng) for p in people}
    records: list[ObservedRecord] = []
    truth: dict[str, TruthRow] = {}

    for p in people:
        if p.id not in visible:
            continue
        boss, hops = by_id.get(p.manager_id), 0
        while boss is not None and boss.id not in visible:
            boss, hops = by_id.get(boss.manager_id), hops + 1
        tags = ["skip_level"] if hops else []
        contractor = p.level >= SENIOR and p.id not in managers and rng.random() < rates.contractors
        if contractor:
            tags.append("contractor")
        records.append(ObservedRecord(p.id, p, names[p.id], "employee", contractor))
        truth[p.id] = TruthRow(p.id, "employee", p.id, p.manager_id, boss.id if boss else None, hops, tags=tags)

    # 2. Duplicates of visible people.
    for rec in [r for r in records if rng.random() < rates.duplicates]:
        key = f"{rec.key}#dup"
        orig = truth[rec.key]
        records.append(ObservedRecord(key, rec.person, _name_variant(rec.name, rng), "duplicate", rec.contractor))
        truth[key] = TruthRow(key, "duplicate", orig.true_person_id, orig.true_manager_id, orig.expected_manager,
                              orig.hops, duplicate_of=rec.key, tags=orig.tags + ["duplicate"])

    # 3. Ghosts: copies of real roles (managers over-weighted) with an earlier start date.
    floor = min(p.start_date for p in people)
    weights = [3.0 if p.id in managers and p.level > CEO else (0.0 if p.level == CEO else 1.0) for p in people]
    for i in range(round(rates.ghosts * len(people))):
        orig = rng.choices(people, weights=weights)[0]
        ghost = dataclasses.replace(orig, id=f"ghost-{i}", manager_id=None,
                                    start_date=_earlier(orig.start_date, floor, rng),
                                    prev_employer=None if rng.random() < 0.4 else orig.prev_employer)
        key = ghost.id
        records.append(ObservedRecord(key, ghost, make_name(rng), "ghost"))
        truth[key] = TruthRow(key, "ghost", None, None, None, tags=["ghost"])

    return records, truth


if __name__ == "__main__":
    import collections

    from .builder import build_company, sample_company_size
    from .clues import add_clues, make_employer_pool
    from .fields import NameMaker
    from .templates import INDUSTRIES

    rng = random.Random(8)
    pool, names = make_employer_pool(rng), NameMaker(8)
    for level in POP_RATES:
        stats = collections.Counter()
        for i in range(60):
            ind = list(INDUSTRIES)[i % len(INDUSTRIES)]
            size = sample_company_size(rng)
            people = build_company(f"c{i}", ind, size, rng)
            add_clues(people, ind, size, rng, pool)
            records, truth = build_population(people, level, rng, names.make)
            stats["true staff"] += len(people)
            stats["records"] += len(records)
            for t in truth.values():
                stats[t.kind] += 1
                stats["skip-level lines"] += t.hops > 0
                stats["contractors"] += "contractor" in t.tags
                stats["no expected manager (excl. ghosts, CEO)"] += t.kind != "ghost" and t.expected_manager is None \
                    and t.true_manager_id is not None
        s = stats
        print(f"{level:<7} {s['records']:>6} records from {s['true staff']:>6} real staff | "
              f"missing {1 - s['employee'] / s['true staff']:.1%} | ghosts {s['ghost']} | dups {s['duplicate']} | "
              f"contractors {s['contractors']} | skip-level {s['skip-level lines'] / s['employee']:.1%} of lines")
