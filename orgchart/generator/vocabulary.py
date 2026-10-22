"""Real-world title spellings, generated once with Gemini and committed as vocab.json.

For every canonical title in the templates we ask Gemini for the different ways
people actually write that *same* role. LLM output can quietly change meaning
("Engineering Manager" -> "Engineering Lead"), which would corrupt the answer key,
so every variant is validated and rejections are kept in the file for review.

Seniority prefixes (Senior / Snr / Sr. / II) are applied by rules in the mess layer,
so Gemini only sees base IC roles.

Run `uv run python -m orgchart.generator.vocabulary` to (re)build vocab.json.
"""

import json
import re
from datetime import date
from pathlib import Path

from .. import llm
from .builder import EXEC_OFFICE
from .templates import CEO, FUNCTIONS, HEAD, INDUSTRIES, LEVEL_NAMES, MID, SENIOR

VOCAB_PATH = Path(__file__).with_name("vocab.json")
BATCH = 25

# Words that signal seniority. A variant may not introduce a family the canonical
# title doesn't already have: that would silently promote or demote the person.
SENIORITY_FAMILIES = {
    "senior": {"senior", "snr", "sr"}, "junior": {"junior", "jr", "jnr"}, "graduate": {"graduate", "grad"},
    "intern": {"intern", "internship"}, "lead": {"lead", "leader", "lead's"},
    # Head and Director are the same level in our model and real data swaps them freely.
    "head_director": {"head", "director", "dir"},
    # C-suite acronyms already mean "chief", so "CEO" -> "Chief Executive Officer" is fine.
    "chief": {"chief", "ceo", "cto", "cfo", "coo", "cio", "cmo", "cro", "cpo", "ciso", "cdo", "cso"},
    # EVP / SVP outrank VP; AVP is below it. Each is its own level.
    "vp": {"vp", "vice"}, "evp_svp": {"evp", "svp"}, "avp": {"avp"},
    "manager": {"manager", "mgr", "mngr", "gm"}, "principal": {"principal"}, "staff": {"staff"},
    "assistant": {"assistant", "asst"}, "associate": {"associate", "assoc"}, "partner": {"partner"},
    "supervisor": {"supervisor", "supv"},
}
_TOKEN = re.compile(r"[a-z']+")


def _families(title: str) -> set[str]:
    tokens = set(_TOKEN.findall(title.lower()))
    return {fam for fam, words in SENIORITY_FAMILIES.items() if tokens & words}


def _norm(title: str) -> str:
    return " ".join(_TOKEN.findall(title.lower().replace("&", " and ")))


def canonical_titles() -> dict[str, dict]:
    """Every canonical title -> {department, level}. Base IC roles count as mid-level."""
    out: dict[str, dict] = {}

    def add(title: str, dept: str, level: int) -> None:
        out.setdefault(title, {"department": dept, "levels": set()})["levels"].add(level)

    for ind in INDUSTRIES.values():
        for t in ind.ceo_titles:
            add(t, "Executive", CEO)
    add("Chief of Staff", "Executive", HEAD)
    add("Executive Assistant to the CEO", "Executive", MID)
    add("Executive Assistant", "Executive", MID)
    for f in FUNCTIONS.values():
        for level, t in f.ladder.items():
            add(t, f.label, level)
        if f.big_head_title:
            add(f.big_head_title[1], f.label, HEAD)
        for role in f.ic_roles:
            if isinstance(role, tuple):
                for i, t in enumerate(role):
                    add(t, f.label, SENIOR + i)
            else:
                add(role, f.label, MID)
    return out


PROMPT = """You are helping build a realistic synthetic dataset of employee job titles as they appear
on LinkedIn profiles and CRM records at Australian companies.

For each canonical job title below, list 12 to 20 different ways real people write that SAME role.

Rules:
- Same role, same seniority, same department. Never promote or demote: do not add or remove
  words like Senior, Lead, Head, Principal, Director, Manager, Chief, VP, Junior or Graduate
  unless the canonical title already means that.
- Do include: common abbreviations (VP, Dir, Mgr, Eng, Ops, Mktg, Acct), acronyms (CTO, CFO, BDR, RN),
  word reordering ("Director of Engineering" vs "Engineering Director"), "&" vs "and",
  Australian/UK spellings, commas and dashes, informal and industry-specific variants.
- Do NOT include: team, product or region names (we add those), typos (we add those),
  capitalisation-only changes, or emojis.

Input (JSON list):
{items}

Return a JSON object whose keys are exactly the canonical "title" values above and whose values are
lists of variant strings."""


def _validate(canonical: dict[str, dict], raw: dict[str, list]) -> tuple[dict, dict]:
    """Drop variants that change meaning or are ambiguous across levels."""
    keep: dict[str, list[str]] = {t: [] for t in canonical}
    rejected: dict[str, list[dict]] = {}
    canon_norm = {_norm(t): t for t in canonical}

    def reject(t: str, v: str, reason: str) -> None:
        rejected.setdefault(t, []).append({"variant": v, "reason": reason})

    for t, variants in raw.items():
        if t not in canonical:
            continue
        seen = {_norm(t)}
        for v in variants if isinstance(variants, list) else []:
            if not isinstance(v, str) or not v.strip():
                continue
            v = v.strip()
            n = _norm(v)
            if n in seen:
                continue
            seen.add(n)
            if len(v) > 70:
                reject(t, v, "too long")
            elif n in canon_norm and canon_norm[n] != t:
                reject(t, v, f"is another canonical title ({canon_norm[n]})")
            elif extra := _families(v) - _families(t):
                reject(t, v, f"adds seniority words: {', '.join(sorted(extra))}")
            else:
                keep[t].append(v)

    # The same spelling offered for roles at different levels is ambiguous: drop it everywhere.
    owners: dict[str, set[str]] = {}
    for t, vs in keep.items():
        for v in vs:
            owners.setdefault(_norm(v), set()).add(t)
    for n, ts in owners.items():
        levels = [canonical[t]["levels"] for t in ts]
        if len(ts) > 1 and any(l != levels[0] for l in levels):
            for t in ts:
                v = next(v for v in keep[t] if _norm(v) == n)
                keep[t].remove(v)
                reject(t, v, f"also offered for {', '.join(sorted(ts - {t}))} at a different level")
    return keep, rejected


def build() -> dict:
    canonical = canonical_titles()
    titles = sorted(canonical)
    raw: dict[str, list] = {}
    for i in range(0, len(titles), BATCH):
        batch = titles[i:i + BATCH]
        items = [{"title": t, "department": canonical[t]["department"],
                  "seniority": " / ".join(LEVEL_NAMES[l] for l in sorted(canonical[t]["levels"]))}
                 for t in batch]
        print(f"  batch {i // BATCH + 1}/{-(-len(titles) // BATCH)}", flush=True)
        raw |= llm.ask_json(PROMPT.format(items=json.dumps(items, indent=1)))
    keep, rejected = _validate(canonical, raw)
    missing = [t for t in titles if t not in raw]
    vocab = {"models": sorted(llm.models_used), "generated": date.today().isoformat(), "missing": missing,
             "titles": keep, "rejected": rejected}
    VOCAB_PATH.write_text(json.dumps(vocab, indent=1, ensure_ascii=False) + "\n")
    return vocab


def load() -> dict[str, list[str]]:
    return json.loads(VOCAB_PATH.read_text())["titles"]


if __name__ == "__main__":
    print(f"{len(canonical_titles())} canonical titles")
    v = build()
    kept = sum(len(x) for x in v["titles"].values())
    dropped = sum(len(x) for x in v["rejected"].values())
    print(f"\nkept {kept} variants, rejected {dropped} ({dropped / (kept + dropped):.0%}), "
          f"missing from Gemini output: {len(v['missing'])}")
    thin = [t for t, vs in v["titles"].items() if len(vs) < 5]
    print(f"titles with fewer than 5 variants: {len(thin)} {thin[:10]}")
