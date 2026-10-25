"""The web API: companies, their inferred org chart at a strictness, why each line
was drawn, and (since the data is synthetic) a grade against the answer key.

    uv run uvicorn orgchart.api.app:app --reload
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from ..evaluation.scorecard import WRONG, _outcome, score
from ..inference.assemble import assemble
from ..inference.engines import PRESETS
from ..inference.features import FEATURES
from ..inference.model import load_model
from ..inference.titles import CEO
from .store import CompanyView, answer_key, company_ids, company_index, view

LEVELS = ["CEO", "C-suite", "VP", "Head / Director", "Senior Manager", "Manager", "Senior IC", "IC", "Junior"]
PRESET_STATS = {p["name"]: p for p in json.loads((Path(__file__).with_name("presets.json")).read_text())}
MIN_CLUE = 0.15   # smallest effect on the score worth showing as a clue

app = FastAPI(title="Org chart inference")


def _view(cid: str) -> CompanyView:
    if cid not in company_ids():
        raise HTTPException(404, f"no company {cid}")
    return view(cid)


def _preset(name: str) -> tuple[float, float]:
    if name not in PRESETS:
        raise HTTPException(400, f"preset must be one of {list(PRESETS)}")
    return PRESETS[name]


def _predictions(v: CompanyView, preset: str):
    exact_t, partial_t = _preset(preset)
    return assemble(v.scored, exact_t, partial_t, v.anc)


def _brief(v: CompanyView, rid: str) -> dict:
    r = v.people[rid].rec
    return {"id": rid, "name": r.name, "title": r.title}


@app.get("/api/presets")
def presets() -> list[dict]:
    return list(PRESET_STATS.values())


@app.get("/api/companies")
def companies(q: str = "", industry: str = "") -> list[dict]:
    q, industry = q.lower().strip(), industry.lower().strip()
    return [{k: c[k] for k in ("company_id", "name", "industry", "headcount_band", "hq", "records")}
            for c in company_index()
            if (not q or q in c["name"].lower()) and (not industry or industry == c["industry"].lower())]


@app.get("/api/companies/{cid}/chart")
def chart(cid: str, preset: str = Query("strict")) -> dict:
    v = _view(cid)
    scored = {s.person.rec.record_id: s for s in v.scored}
    people, counts = [], {"exact": 0, "partial": 0, "root": 0, "unplaced": 0}
    for p in _predictions(v, preset):
        person, s = v.people[p.record_id], scored[p.record_id]
        if p.kind != "none":
            placement = p.kind
        elif person.level == CEO and person.level_known and not s.options:
            placement = "root"
        else:
            placement = "unplaced"
        counts[placement] += 1
        r = person.rec
        people.append({
            "id": r.record_id, "name": r.name, "title": r.title, "department": r.department,
            "location": r.location, "start_date": r.start_date,
            "level": LEVELS[person.level] if person.level_known else None,
            "function": person.function, "manager_id": p.manager_id, "placement": placement,
            "confidence": round(p.confidence, 3),
            **(_unplaced(s) if placement == "unplaced" else {"reason": p.reason}),
        })
    c = v.company
    return {"company": {"company_id": c.company_id, "name": c.name, "industry": c.industry,
                        "headcount_band": c.headcount_band, "hq": c.hq},
            "preset": PRESET_STATS[preset], "counts": counts, "people": people}


def _unplaced(s) -> dict:
    """Why someone wasn't placed, as a code the app groups by, plus our best guess."""
    if not s.options:
        return {"reason_code": "no_candidates", "reason": "no one in the data looks senior enough to be their boss"}
    boss, boss_p = s.options[0]
    guess = {"best_guess_id": boss, "best_guess_p": round(boss_p, 3)}
    if s.p_none >= boss_p and s.p_none >= 0.5:
        return {"reason_code": "ghost_like", **guess,
                "reason": f"probably no boss here ({s.p_none:.0%}): possibly a stale profile or someone who left"}
    return {"reason_code": "uncertain", **guess, "reason": f"too uncertain: best guess only {boss_p:.0%}"}


# -- why --------------------------------------------------------------------------------------------
_F = {name: i for i, name in enumerate(FEATURES)}


def _clues(person, boss, x: list[float]) -> list[dict]:
    """Evidence a person can check (team, office, dates, ex-colleagues, ghost signs). Level-gap
    and exec weights are left out: they offset each other and read as nonsense on their own."""
    w = load_model()["weights"]
    labels = {
        "same_team": f"same team ({person.team})", "team_mismatch": f"different team ({person.team} vs {boss.team})",
        "same_city": f"same office ({person.city})", "city_differs": f"different office ({person.city} vs {boss.city})",
        "boss_started_first": "joined before them", "boss_started_after": "joined after them",
        "burst_6m": "they joined within 6 months of this boss", "same_employer": f"both came from {person.employer}",
        "closest_level_in_function": "nearest manager level in the department",
        "dept_leak": "their department field names this boss's department",
        "boss_is_older_echo": "looks like an old profile of a current role (possible ghost)",
        "boss_is_oldest_twin": "earliest of several look-alike roles (possible ghost)",
        "boss_cannot_manage": "title rarely manages anyone (assistant, contractor)",
        "boss_level_unknown": "boss's title is unreadable",
        "ceo_over_exec": "C-suite usually reports to the CEO",
        "ceo_over_unled_head": "no VP or exec in their department, so likely the CEO",
    }
    out = []
    for name, text in labels.items():
        effect = w[_F[name]] * x[_F[name]]
        if x[_F[name]] and abs(effect) >= MIN_CLUE:
            out.append({"clue": text, "effect": round(effect, 2)})
    return sorted(out, key=lambda c: -abs(c["effect"]))


@app.get("/api/companies/{cid}/people/{rid}/why")
def why(cid: str, rid: str, preset: str = Query("strict")) -> dict:
    v = _view(cid)
    if rid not in v.people:
        raise HTTPException(404, f"no record {rid} in {cid}")
    person = v.people[rid]
    s = next(s for s in v.scored if s.person.rec.record_id == rid)
    decision = next(p for p in _predictions(v, preset) if p.record_id == rid)
    parsed = person.parsed
    candidates = []
    for boss_id, prob in s.options[:len(v.pairs.get(rid, {}))]:
        boss = v.people[boss_id]
        candidates.append({**_brief(v, boss_id), "probability": round(prob, 3),
                           "clues": _clues(person, boss, v.pairs[rid][boss_id].x)})
    ups = sorted(((a, m) for a, m in v.anc.get(rid, {}).items() if v.people[a].level != CEO),
                 key=lambda t: -t[1])[:3]
    return {
        "person": {**_brief(v, rid), "department": person.rec.department, "location": person.rec.location,
                   "start_date": person.rec.start_date, "prev_employer": person.rec.prev_employer},
        "read_as": {"level": LEVELS[person.level] if person.level_known else None,
                    "department": person.function, "team": person.team, "office": person.city,
                    "confidence": round(parsed.confidence, 2), "rule": parsed.rule, "flags": sorted(parsed.flags)},
        "decision": {"kind": decision.kind, "manager": _brief(v, decision.manager_id) if decision.manager_id else None,
                     "confidence": round(decision.confidence, 3), "reason": decision.reason},
        "candidates": candidates,
        "probability_no_boss_here": round(s.p_none, 3),
        "reports_up_to": [{**_brief(v, a), "probability": round(m, 3)} for a, m in ups],
    }


# -- grade ------------------------------------------------------------------------------------------
@app.get("/api/companies/{cid}/grade")
def grade(cid: str, preset: str = Query("strict")) -> dict:
    v = _view(cid)
    truth = answer_key(cid)
    if truth is None:
        raise HTTPException(404, "no answer key for this dataset")
    preds = _predictions(v, preset)
    lines = {}
    for p in preds:
        outcome, gap = _outcome(p, truth.chain[p.record_id])
        nearest = truth.chain[p.record_id][0] if truth.chain[p.record_id] else frozenset()
        correct = min(nearest) if nearest else None
        lines[p.record_id] = {"outcome": outcome, "wrong": outcome in WRONG, "levels_above_manager": gap,
                              "kind": truth.kind[p.record_id],
                              "correct_manager": _brief(v, correct) if correct else None}
    m = score(preds, truth)
    split = next(c.get("split") for c in company_index() if c["company_id"] == cid)
    return {"mess_level": truth.mess_level[cid], "split": split,
            "scorecard": {k: m[k] for k in ("records", "claims", "wrong", "precision", "wrong_per_1k",
                                            "exact_coverage", "useful_coverage", "attached_to_ghost", "outcomes")},
            "lines": lines}


# -- the React app (web/dist, built with `npm run build`), mounted last so /api wins -------------------
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
