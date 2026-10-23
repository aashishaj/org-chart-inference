"""Generates the full dataset: 600 companies, public flat files plus a hidden answer key.

    data/companies.csv          public: what any data provider would know
    data/people.csv             public: one messy row per record, no manager column
    data/truth/people.csv       hidden: correct answer and mess tags per record
    data/truth/true_tree.csv    hidden: the real org, including people missing from the data
    data/truth/companies.csv    hidden: mess level, inflation, offices, founding year

Inference code must only ever read the public files.

Run `uv run python -m orgchart.generator.generate` (about a minute).
"""

import argparse
import csv
import random
import time
from pathlib import Path

from .builder import build_company, sample_company_size
from .clues import add_clues, make_employer_pool
from .fields import NameMaker, department_owners, render_fields
from .mess import PROFILES, TitleContext, pick_profile, render_title
from .population import build_population, contractor_title
from .templates import INDUSTRIES
from .vocabulary import load

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MIN_VISIBLE_EMPLOYEES = 100

# -- company names ----------------------------------------------------------------------------
_WORDS = ["Harbour", "Southern Cross", "Bluegum", "Ironbark", "Wattle", "Banksia", "Redgum", "Kestrel", "Tasman",
          "Coral", "Eureka", "Granite", "Summit", "Meridian", "Northstar", "Silverleaf", "Riverbend", "Lighthouse",
          "Brightwater", "Arcadia", "Coastal", "Highland", "Outback", "Sterling", "Pacific", "Koala", "Magpie",
          "Jarrah", "Boab", "Kookaburra", "Saltbush", "Spinifex", "Waratah", "Acacia", "Mallee", "Brolga",
          "Cassowary", "Kingfisher", "Echidna", "Platypus", "Opal", "Sapphire", "Basalt", "Sandstone", "Driftwood"]
_PLACES = ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Hunter", "Illawarra", "Gippsland", "Riverina",
           "Pilbara", "Goldfields", "Sunshine Coast", "Barossa", "Derwent", "Murray", "Coral Coast"]
_SURNAMES = ["Hartley", "Fitzgerald", "Mackenzie", "Whitlam", "Barton", "Deakin", "Lawson", "Paterson", "Monash",
             "Sturt", "Flinders", "Bligh", "Macquarie", "Hargrave", "Florey"]
_PATTERNS = {
    "saas": ["{w}ly", "{w} Labs", "{w} AI", "{w}HQ", "{w} Cloud", "{w} Software", "Get{w}"],
    "financial_services": ["{p} Bank", "{w} Capital", "{w} Mutual", "{p} Credit Union", "{w} Finance", "{w} Wealth"],
    "healthcare": ["{p} Health", "{w} Medical Group", "{w} Healthcare", "{p} Private Hospitals", "{w} Care"],
    "retail": ["{w} & Co", "{w} Home", "{w} Outfitters", "{w} Living", "{w} Supply Co"],
    "mining": ["{w} Resources", "{w} Minerals", "{p} Mining", "{w} Metals", "{w} Gold"],
    "professional_services": ["{s} {s2} & Partners", "{w} Advisory", "{s} & Co", "{w} Consulting", "{s} Legal"],
    "manufacturing": ["{w} Industries", "{w} Manufacturing", "{p} Steel", "{w} Engineering", "{w} Plastics"],
    "education": ["{p} Institute of Technology", "{w} College", "{p} Business School", "{w} Academy"],
    "construction": ["{w} Constructions", "{w} Property Group", "{w} Civil", "{p} Builders", "{w} Developments"],
    "logistics": ["{w} Freight", "{w} Logistics", "{p} Transport", "{w} Express", "{w} Couriers"],
}


def company_name(industry: str, rng: random.Random, taken: set[str]) -> str:
    for _ in range(1000):
        s, s2 = rng.sample(_SURNAMES, 2)
        name = rng.choice(_PATTERNS[industry]).format(w=rng.choice(_WORDS), p=rng.choice(_PLACES), s=s, s2=s2)
        if name not in taken:
            taken.add(name)
            return name
    raise RuntimeError("ran out of company names")


def headcount_band(n: int) -> str:
    for lo, hi in [(51, 200), (201, 500), (501, 1000), (1001, 5000)]:
        if n <= hi:
            return f"{lo}-{hi}"
    return "5001+"


# -- writer ---------------------------------------------------------------------------------------
PUBLIC_PEOPLE = ["record_id", "company_id", "name", "title", "department", "location", "start_date", "prev_employer"]
TRUTH_PEOPLE = ["record_id", "company_id", "kind", "expected_manager_id", "hops", "duplicate_of", "true_person_id",
                "true_manager_person_id", "canonical_title", "function", "level", "team", "true_location",
                "true_start_date", "mess_tags"]
TRUE_TREE = ["person_id", "company_id", "manager_person_id", "canonical_title", "function", "level", "team",
             "location", "start_date", "record_id"]


def generate(n_companies: int = 600, seed: int = 2026, out: Path = DATA_DIR) -> dict:
    master = random.Random(seed)
    vocab = load()
    names = NameMaker(seed)

    # Plan every company first so their names can join the previous-employer pool.
    plans, taken = [], set()
    for i in range(n_companies):
        industry = master.choices(list(INDUSTRIES), weights=[x.weight for x in INDUSTRIES.values()])[0]
        plans.append({"company_id": f"C{i + 1:04d}", "industry": industry, "size": sample_company_size(master),
                      "profile": pick_profile(master).name, "name": company_name(industry, master, taken)})
    pool = make_employer_pool(master)
    pool = master.sample(pool + [p["name"] for p in plans], len(pool) + len(plans))

    (out / "truth").mkdir(parents=True, exist_ok=True)
    files = {k: open(out / path, "w", newline="") for k, path in [
        ("companies", "companies.csv"), ("people", "people.csv"), ("t_people", "truth/people.csv"),
        ("t_tree", "truth/true_tree.csv"), ("t_companies", "truth/companies.csv")]}
    w = {
        "companies": csv.DictWriter(files["companies"], ["company_id", "name", "industry", "headcount_band", "hq"]),
        "people": csv.DictWriter(files["people"], PUBLIC_PEOPLE),
        "t_people": csv.DictWriter(files["t_people"], TRUTH_PEOPLE),
        "t_tree": csv.DictWriter(files["t_tree"], TRUE_TREE),
        "t_companies": csv.DictWriter(files["t_companies"], ["company_id", "mess_level", "inflated", "size",
                                                             "offices", "founded"]),
    }
    for writer in w.values():
        writer.writeheader()

    totals = {"records": 0, "true_people": 0}
    used_ids: set[str] = set()
    try:
        for i, plan in enumerate(plans):
            cid, industry, size, profile = plan["company_id"], plan["industry"], plan["size"], PROFILES[plan["profile"]]
            # The brief asks for 100+ employees per company, and reviewers will count visible
            # rows. Missing employees can push a small company under, so grow it and retry.
            for attempt in range(20):
                rng = random.Random(seed * 100_003 + i * 31 + attempt)  # per-company seed
                names.reseed(seed * 100_003 + i * 31 + attempt)
                people = build_company(cid, industry, size, rng)
                facts = add_clues(people, industry, size, rng, pool, profile.clues)
                for p in people:
                    if p.prev_employer == plan["name"]:
                        p.prev_employer = None  # nobody's previous employer is their current one
                records, truth = build_population(people, profile.name, rng, names.make)
                if sum(t.kind == "employee" for t in truth.values()) >= MIN_VISIBLE_EMPLOYEES:
                    break
                size += 10
            managers = {p.manager_id for p in people if p.manager_id}
            owners = department_owners(people)
            inflated = size < 300 and rng.random() < profile.inflate_company

            # Opaque ids, assigned in shuffled order so neither ids nor row order leak structure.
            rng.shuffle(records)
            rid = {}
            for r in records:
                while (new := f"{rng.getrandbits(32):08x}") in used_ids:
                    pass
                used_ids.add(new)
                rid[r.key] = new

            ctx_base = dict(profile=profile, vocab=vocab, company_name=plan["name"], industry=industry, inflated=inflated)
            for r in records:
                p, t = r.person, truth[r.key]
                is_mgr = p.id in managers and r.kind != "ghost"
                title, title_tags = render_title(p, TitleContext(**ctx_base, is_manager=is_mgr), rng)
                if r.contractor:
                    title = contractor_title(title, rng)
                rec, field_tags = render_fields(p, title, profile.name, owners, r.name, rng)
                w["people"].writerow({"record_id": rid[r.key], "company_id": cid, **rec})
                w["t_people"].writerow({
                    "record_id": rid[r.key], "company_id": cid, "kind": t.kind,
                    "expected_manager_id": rid.get(t.expected_manager, ""), "hops": t.hops,
                    "duplicate_of": rid.get(t.duplicate_of, ""), "true_person_id": t.true_person_id or "",
                    "true_manager_person_id": t.true_manager_id or "", "canonical_title": p.title,
                    "function": p.function, "level": p.level, "team": p.team or "", "true_location": p.location,
                    "true_start_date": p.start_date, "mess_tags": ";".join(t.tags + title_tags + field_tags)})
            for p in people:
                w["t_tree"].writerow({
                    "person_id": p.id, "company_id": cid, "manager_person_id": p.manager_id or "",
                    "canonical_title": p.title, "function": p.function, "level": p.level, "team": p.team or "",
                    "location": p.location, "start_date": p.start_date, "record_id": rid.get(p.id, "")})
            w["companies"].writerow({"company_id": cid, "name": plan["name"], "industry": INDUSTRIES[industry].label,
                                     "headcount_band": headcount_band(len(people)), "hq": facts["offices"][0]})
            w["t_companies"].writerow({"company_id": cid, "mess_level": profile.name, "inflated": inflated,
                                       "size": len(people), "offices": ";".join(facts["offices"]),
                                       "founded": facts["founded"]})
            totals["records"] += len(records)
            totals["true_people"] += len(people)
    finally:
        for f in files.values():
            f.close()
    return totals


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--companies", type=int, default=600)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", type=Path, default=DATA_DIR)
    args = ap.parse_args()
    t0 = time.time()
    totals = generate(args.companies, args.seed, args.out)
    print(f"{args.companies} companies, {totals['true_people']:,} real people, {totals['records']:,} records "
          f"-> {args.out} in {time.time() - t0:.0f}s")
