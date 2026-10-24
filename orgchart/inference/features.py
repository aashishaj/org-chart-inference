"""Turns a company's public records into candidate (person, boss) pairs with features.

Per record: parsed title (rules + Gemini), city, start date, team words, department
field function, previous employer. Per pair: the features the learned model weighs.

Everything here is public-data only. The learned bits (department-pair priors and
model weights) are loaded from model.json, written by orgchart/evaluation/train.py.
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .data import Company, Record
from .llm_titles import parse_title_hybrid
from .titles import CEO, EXEC, HEAD, MGR, MID, VP, ParsedTitle, department_function

UNKNOWN_LEVEL = MID  # a title we can't read is most likely an IC

# -- record-level parsing ----------------------------------------------------------------------
_STATES = re.compile(r"\s+(nsw|vic|qld|wa|sa|act|tas|nt|au)$")
_REMOTE = re.compile(r"\bremote\b|work from home|\bwfh\b")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                        "dec"], 1)}


def city_of(location: str) -> str | None:
    """'Greater Sydney Area', 'Sydney NSW', 'Sydney, New South Wales, Australia' -> 'sydney'."""
    s = location.lower().strip()
    if not s or _REMOTE.search(s):
        return None
    s = s.replace("greater ", "").replace(" area", "").split(",")[0].strip()
    return _STATES.sub("", s).strip() or None


def months_of(start: str) -> tuple[float | None, bool]:
    """Any start-date format -> (months since year 0, exact month known)."""
    s = start.strip().lower()
    if not s:
        return None, False
    if m := re.fullmatch(r"(\d{4})", s):
        return int(m[1]) * 12 + 6, False
    if m := re.fullmatch(r"(\d{4})[-/](\d{1,2})", s):
        return int(m[1]) * 12 + int(m[2]), True
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", s):
        return int(m[2]) * 12 + int(m[1]), True
    if m := re.fullmatch(r"([a-z]+)\s+(\d{4})", s):
        if (mon := _MONTHS.get(m[1][:3])) is not None:
            return int(m[2]) * 12 + mon, True
    return None, False


_FUNCTION_WORDS = re.compile(r"\b(engineering|software|sales|marketing|finance|data|product|design|security|"
                             r"operations|senior|junior|graduate|manager|team|lead)\b")


def team_of(p: ParsedTitle) -> str | None:
    """The team/specialty qualifier, minus words that just repeat the department."""
    for q in p.qualifiers:
        t = _FUNCTION_WORDS.sub("", q).strip(" -,&")
        if len(t) >= 2:
            return t
    return None


def _employer(s: str) -> str | None:
    s = re.sub(r"\b(pty|ltd|limited|co|group|holdings)\b\.?", "", s.lower()).strip(" ,.")
    return s or None


@dataclass
class Person:
    rec: Record
    parsed: ParsedTitle
    level: int              # UNKNOWN_LEVEL when unreadable
    level_known: bool
    function: str | None    # title first, department field as fallback
    dept_function: str | None
    city: str | None
    start: float | None
    start_exact: bool
    team: str | None
    employer: str | None

    @property
    def can_manage(self) -> bool:
        return "assistant" not in self.parsed.rule and "contractor" not in self.parsed.flags


def read_company(company: Company) -> list[Person]:
    out = []
    for r in company.records:
        p = parse_title_hybrid(r.title, company.industry)
        dept_fn = department_function(r.department)
        start, exact = months_of(r.start_date)
        out.append(Person(r, p, p.level if p.level is not None else UNKNOWN_LEVEL, p.level is not None,
                          p.function or dept_fn, dept_fn, city_of(r.location), start, exact, team_of(p),
                          _employer(r.prev_employer)))
    return out


# -- candidates and pair features -----------------------------------------------------------------
FEATURES = [
    "bias", "gap1", "gap2", "gap3", "gap4plus", "boss_exec", "boss_ceo",
    "same_function", "log_pair_prior", "closest_level_in_function", "dept_leak",
    "same_team", "team_mismatch", "boss_team_unknown",
    "same_city", "city_differs", "city_unknown",
    "boss_started_first", "boss_started_after", "start_unknown", "burst_6m", "log_months_after",
    "same_employer", "log_same_title_peers", "boss_twin_count_log", "boss_is_oldest_twin",
    "boss_cannot_manage", "boss_level_unknown", "person_level_unknown", "boss_parse_conf", "boss_reports_hint",
    "boss_is_older_echo", "ceo_over_exec", "ceo_over_unled_head",
]
F = {name: i for i, name in enumerate(FEATURES)}


def _is_oldest_twin(p: Person, others: list[Person]) -> float:
    starts = [t.start for t in others if t.start is not None]
    return float(p.start is not None and bool(starts) and p.start < min(starts))


# Features of the "none of these" option, per person: when should nobody be the boss?
NONE_FEATURES = ["none_bias", "is_oldest_twin", "twin_count_log", "level_unknown", "is_top_level",
                 "title_blank", "is_contractor", "is_older_echo", "is_older_echo_manager"]


def older_echoes(people: list[Person]) -> set[str]:
    """Records that look like an earlier holder of someone else's job: same department,
    level, team and previous employer, but started earlier. A ghost profile is exactly
    this (the person left, their replacement joined later); two real colleagues rarely
    share all four."""
    groups = defaultdict(list)
    for p in people:
        if p.function and p.employer and p.start is not None:
            groups[(p.function, p.level, p.team, p.employer)].append(p)
    out = set()
    for g in groups.values():
        if len(g) > 1:
            latest = max(p.start for p in g)
            out |= {p.rec.record_id for p in g if p.start < latest - 1}
    return out


def none_features(people: list[Person]) -> dict[str, list[float]]:
    _, twins, _, echoes = _company_context(people)
    out = {}
    for p in people:
        tw = [t for t in twins.get(_twin_key(p), []) if t is not p]
        echo = p.rec.record_id in echoes
        out[p.rec.record_id] = [1.0, _is_oldest_twin(p, tw), math.log1p(len(tw)), float(not p.level_known),
                                float(p.level <= EXEC), float(not p.rec.title), float("contractor" in p.parsed.flags),
                                float(echo), float(echo and p.level <= MGR)]
    return out


@dataclass
class Pair:
    person: str
    boss: str
    x: list[float]


def _twin_key(p: Person) -> tuple | None:
    """Same department, level and team. Not title text: a ghost's title is usually spelled
    differently from the real holder's ("Sales Mgr" vs "Manager - Sales")."""
    return (p.function, p.level, p.team) if p.level <= MGR and p.function else None


def _company_context(people: list[Person]):
    peers = Counter((p.function, p.level, p.parsed.core) for p in people if p.level <= MGR)
    twins = defaultdict(list)  # same role: one is often a ghost (the predecessor who left)
    for p in people:
        if (k := _twin_key(p)) is not None:
            twins[k].append(p)
    # How many plausible reports each manager-level record has in their own function: a
    # "manager" with nobody below them in their department is suspicious (ghost or stale title).
    by_function_level = Counter((p.function, p.level) for p in people)
    return peers, twins, by_function_level, older_echoes(people)


TIER_A_MAX = 80   # same department, closest level above: where the boss usually is, never pruned by a guess
TIER_B_MAX = 30   # same department, further up (skip-levels, missing middle managers)
TIER_R_MAX = 30   # closely related departments (Supply Chain under Operations), or no department known
TIER_C_MAX = 15   # other departments, ranked by the learned department-pair prior
RELATED_PRIOR = 0.05


def _pre_score(p: Person, b: Person, prior: float) -> float:
    """Cheap ranking used only to trim tiers; the full features are computed for survivors."""
    s = 0.3 * math.log(prior + 1e-4) - 0.5 * max(0, p.level - b.level - 2)
    if p.team and b.team:
        s += 1 if p.team == b.team else -1
    if p.city and b.city:
        s += 1 if p.city == b.city else -0.5
    if p.start is not None and b.start is not None:
        s += 1 if b.start <= p.start else -0.5
    if p.employer and p.employer == b.employer:
        s += 2
    return s - (not b.can_manage)


def candidate_pairs(people: list[Person], pair_prior: dict[tuple[str, str], float]) -> list[Pair]:
    """Candidate bosses for everyone, in tiers so the likeliest boss is never pruned away.

    Tier A: same department, the closest *manager-level* rank above the person (all of
    them: this is where the boss usually is). Tier B: the rest of the department above
    them, including senior ICs (a promoted manager's profile can still say "Senior").
    Execs: always (there are few, and every department head reports to one).
    Tier R: managers in closely related departments, or any manager when the person's
    department is unknown. Tier C: other departments, by the learned department-pair prior.
    """
    peers, twins, by_fl, echoes = _company_context(people)
    seniors = [b for b in people if b.level < UNKNOWN_LEVEL]
    out = []
    for p in people:
        if p.level == CEO and p.level_known:
            continue
        above = [b for b in seniors if b is not p and b.level < p.level]
        same_fn = {id(b) for b in above if p.function is not None and b.function == p.function}
        closest = max((b.level for b in above if id(b) in same_fn and b.level <= MGR), default=None)
        # A department with no visible VP or exec: its head most likely reports to the CEO.
        unled = not any(b.level <= VP for b in above if id(b) in same_fn)
        tier_a, tier_b, execs, tier_r, tier_c = [], [], [], [], []
        for b in above:
            prior = pair_prior.get((p.function or "?", b.function or "?"), 0.0)
            if id(b) in same_fn:
                (tier_a if b.level == closest else tier_b).append((b, prior))
            elif b.level <= EXEC:
                execs.append((b, prior))
            elif b.level <= MGR and (p.function is None or prior >= RELATED_PRIOR):
                tier_r.append((b, prior))
            elif prior >= 0.005:
                tier_c.append((b, prior))
        for tier, cap in ((tier_a, TIER_A_MAX), (tier_b, TIER_B_MAX), (execs, len(execs)), (tier_r, TIER_R_MAX),
                          (tier_c, TIER_C_MAX)):
            if len(tier) > cap:
                tier.sort(key=lambda t: -_pre_score(p, t[0], t[1]))
            for b, prior in tier[:cap]:
                out.append(Pair(p.rec.record_id, b.rec.record_id,
                                _features(p, b, prior, closest, peers, twins, by_fl, echoes, unled)))
    return out


def _features(p: Person, b: Person, prior: float, closest: int | None, peers, twins, by_fl,
              echoes: set[str], unled: bool) -> list[float]:
    x = [0.0] * len(FEATURES)
    gap = p.level - b.level
    x[F["bias"]] = 1
    x[F["gap1" if gap == 1 else "gap2" if gap == 2 else "gap3" if gap == 3 else "gap4plus"]] = 1
    x[F["boss_exec"]] = float(b.level <= EXEC)
    x[F["boss_ceo"]] = float(b.level == CEO)
    x[F["same_function"]] = float(p.function is not None and p.function == b.function)
    x[F["log_pair_prior"]] = math.log(prior + 1e-4)
    x[F["closest_level_in_function"]] = float(b.function == p.function and b.level == closest)
    x[F["dept_leak"]] = float(p.dept_function is not None and p.dept_function == b.function
                              and p.dept_function != p.function)
    if b.team and p.team:
        x[F["same_team"]] = float(b.team == p.team)
        x[F["team_mismatch"]] = float(b.team != p.team)
    else:
        x[F["boss_team_unknown"]] = 1
    if p.city and b.city:
        x[F["same_city"]] = float(p.city == b.city)
        x[F["city_differs"]] = float(p.city != b.city)
    else:
        x[F["city_unknown"]] = 1
    if p.start is not None and b.start is not None:
        after = p.start - b.start
        x[F["boss_started_first"]] = float(after >= 0)
        x[F["boss_started_after"]] = float(after < 0)
        x[F["burst_6m"]] = float(0 <= after <= 6)
        x[F["log_months_after"]] = math.log1p(max(after, 0))
    else:
        x[F["start_unknown"]] = 1
    x[F["same_employer"]] = float(p.employer is not None and p.employer == b.employer)
    x[F["log_same_title_peers"]] = math.log(peers.get((b.function, b.level, b.parsed.core), 1))
    tw = [t for t in twins.get(_twin_key(b), []) if t is not b]
    x[F["boss_twin_count_log"]] = math.log1p(len(tw))
    x[F["boss_is_oldest_twin"]] = _is_oldest_twin(b, tw)
    x[F["boss_cannot_manage"]] = float(not b.can_manage)
    x[F["boss_level_unknown"]] = float(not b.level_known)
    x[F["person_level_unknown"]] = float(not p.level_known)
    x[F["boss_parse_conf"]] = b.parsed.confidence
    # Does the boss's department actually have people one level below them?
    x[F["boss_reports_hint"]] = math.log1p(sum(by_fl.get((b.function, lvl), 0) for lvl in range(b.level + 1,
                                                                                                b.level + 3)))
    x[F["boss_is_older_echo"]] = float(b.rec.record_id in echoes)
    ceo = b.level == CEO and b.level_known
    x[F["ceo_over_exec"]] = float(ceo and p.level == EXEC and p.level_known)
    x[F["ceo_over_unled_head"]] = float(ceo and p.level in (VP, HEAD) and p.level_known and unled)
    return x
