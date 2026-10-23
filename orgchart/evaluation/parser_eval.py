"""Scores the title parser on its own: level and department against the answer key,
broken down by mess tag, plus the most common mistakes (what to fix next).

    uv run python -m orgchart.evaluation.parser_eval            # dev split
"""

import argparse
import csv
import json
from collections import Counter, defaultdict

from ..inference.data import DATA_DIR, load_companies
from ..inference.llm_titles import gemini_parse, parse_title_hybrid
from ..inference.titles import department_function, parse_title
from .run import RUNS_DIR
from .split import SPLITS, companies_in

PARSERS = {"rules": parse_title, "hybrid": parse_title_hybrid}

TAGS = ["variant", "seniority_format", "team", "typo", "casing", "fluff", "vague", "creative", "contractor",
        "acting", "stale", "inflated", "title_missing"]
HIGH_CONF = 0.8


def evaluate(split: str = "dev", show_errors: int = 15, parser: str = "rules") -> dict:
    parse = PARSERS[parser]
    ids = set(companies_in(split))
    companies = load_companies()
    industry = {cid: c.industry for cid, c in companies.items()}
    public = {r.record_id: r for cid in ids for r in companies[cid].records}
    with open(DATA_DIR / "truth" / "people.csv", newline="") as f:
        truth = [t for t in csv.DictReader(f) if t["company_id"] in ids]

    n = Counter()
    by_tag = defaultdict(Counter)
    level_err, func_err = Counter(), Counter()
    for t in truth:
        r = public[t["record_id"]]
        p = parse(r.title, industry[r.company_id])
        true_level, true_fn = int(t["level"]), t["function"]
        fn = p.function or department_function(r.department)
        hit_level = p.level == true_level
        near_level = p.level is not None and abs(p.level - true_level) <= 1
        hit_fn_title = p.function == true_fn
        hit_fn = fn == true_fn
        high = p.confidence >= HIGH_CONF
        n.update({"records": 1, "level_parsed": p.level is not None, "level_exact": hit_level,
                  "level_within_1": near_level, "fn_title": hit_fn_title, "fn_with_dept": hit_fn,
                  "fn_parsed": fn is not None, "high_conf": high, "high_conf_level": high and hit_level,
                  "high_conf_fn": high and hit_fn_title})
        for tag in set(t["mess_tags"].split(";")) & set(TAGS):
            by_tag[tag].update({"n": 1, "level": hit_level, "fn": hit_fn})
        if not hit_level and r.title:
            level_err[(r.title, p.level, true_level)] += 1
        if not hit_fn and r.title:
            func_err[(r.title, fn, true_fn)] += 1

    N = n["records"]
    m = {
        "records": N,
        "level_exact": n["level_exact"] / N, "level_within_1": n["level_within_1"] / N,
        "fn_title_only": n["fn_title"] / N, "fn_with_department": n["fn_with_dept"] / N,
        "unparsed_level": 1 - n["level_parsed"] / N, "unparsed_function": 1 - n["fn_parsed"] / N,
        "high_conf_share": n["high_conf"] / N,
        "high_conf_level_acc": n["high_conf_level"] / n["high_conf"] if n["high_conf"] else None,
        "high_conf_fn_acc": n["high_conf_fn"] / n["high_conf"] if n["high_conf"] else None,
        "by_tag": {tag: {"n": c["n"], "level": c["level"] / c["n"], "fn": c["fn"] / c["n"]}
                   for tag, c in by_tag.items()},
    }
    path = RUNS_DIR / split / f"parser_{parser}.json"
    prev = json.loads(path.read_text()) if path.exists() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, indent=1))

    def line(label, key):
        d = f"   ({m[key] - prev[key]:+.1%})" if prev.get(key) is not None and abs(m[key] - prev[key]) > 1e-9 else ""
        return f"  {label:<44} {m[key]:>7.1%}{d}"

    print(f"\n=== title parser ({parser}) on {split} ({N:,} records) ===")
    for label, key in [("Level exact", "level_exact"), ("Level within one", "level_within_1"),
                       ("Department from title alone", "fn_title_only"),
                       ("Department with department-field fallback", "fn_with_department"),
                       ("No level found", "unparsed_level"), ("No department found", "unparsed_function"),
                       (f"High-confidence parses (>= {HIGH_CONF})", "high_conf_share"),
                       ("  ...their level accuracy", "high_conf_level_acc"),
                       ("  ...their department accuracy", "high_conf_fn_acc")]:
        print(line(label, key))
    print("\n  By mess tag            records   level   department")
    for tag in TAGS:
        if tag in m["by_tag"]:
            b = m["by_tag"][tag]
            print(f"  {tag:<22} {b['n']:>7,}   {b['level']:>5.0%}   {b['fn']:>5.0%}")
    if show_errors:
        print(f"\n  Most common level mistakes (title -> parsed / true):")
        for (title, got, want), c in level_err.most_common(show_errors):
            print(f"    {c:>4}x  {title[:55]:<55} {got} / {want}")
        print(f"\n  Most common department mistakes:")
        for (title, got, want), c in func_err.most_common(show_errors):
            print(f"    {c:>4}x  {title[:55]:<55} {got} / {want}")
    return m


def independent_check() -> None:
    """Rules vs Gemini on a random sample of titles the rules were confident about.

    The rules were written by someone who had seen the generator's spellings; Gemini
    wasn't. If the rules are only good because of that, Gemini will do far better or
    disagree a lot on this sample."""
    companies = load_companies()
    industry = {cid: c.industry for cid, c in companies.items()}
    with open(DATA_DIR / "truth" / "people.csv", newline="") as f:
        truth = {t["record_id"]: t for t in csv.DictReader(f)}
    n = Counter()
    for c in companies.values():
        for r in c.records:
            g = gemini_parse(r.title, c.industry) if r.title else None
            rule = parse_title(r.title, industry[r.company_id]) if r.title else None
            if g is None or rule is None or rule.confidence < 0.7:
                continue  # only the check sample: titles the rules were confident about
            t = truth[r.record_id]
            lvl, fn = int(t["level"]), t["function"]
            n.update({"n": 1, "rules_level": rule.level == lvl, "gemini_level": g.level == lvl,
                      "rules_fn": rule.function == fn, "gemini_fn": g.department == fn,
                      "agree": (rule.level, rule.function) == (g.level, g.department)})
    if not n["n"]:
        print("no check-sample parses yet: run `python -m orgchart.inference.llm_titles`")
        return
    print(f"\n=== independent check: {n['n']:,} records whose titles the rules parsed confidently ===")
    print(f"                 level   department")
    print(f"  rules          {n['rules_level'] / n['n']:>5.1%}   {n['rules_fn'] / n['n']:>5.1%}")
    print(f"  gemini         {n['gemini_level'] / n['n']:>5.1%}   {n['gemini_fn'] / n['n']:>5.1%}")
    print(f"  rules and gemini agree on both: {n['agree'] / n['n']:.1%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=SPLITS)
    ap.add_argument("--errors", type=int, default=15)
    ap.add_argument("--parser", default="rules", choices=list(PARSERS))
    ap.add_argument("--check", action="store_true", help="rules vs Gemini on the independent check sample")
    args = ap.parse_args()
    if args.check:
        independent_check()
    else:
        evaluate(args.split, args.errors, args.parser)
