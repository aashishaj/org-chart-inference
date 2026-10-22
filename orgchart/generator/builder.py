"""Builds one company's *true* org tree from its industry template.

Output is a list of Person records with canonical titles and the real manager_id.
This is the answer key: the inference code never sees manager_id.

Run `uv run python -m orgchart.generator.builder` to print sample companies.
"""

import math
import random
from dataclasses import dataclass

from .templates import (CEO, EXEC, FUNCTIONS, HEAD, INDUSTRIES, JUNIOR, LEVEL_NAMES, MGR, MID, SENIOR, VP,
                        exec_min_size, head_reports_to)

EXEC_OFFICE = "executive"  # pseudo-function for CEO, Chief of Staff and EAs

IC_LEVEL_WEIGHTS = {SENIOR: 0.3, MID: 0.5, JUNIOR: 0.2}
DIRECT_IC_P = 0.3       # chance a manager-of-managers also has 1-2 ICs reporting directly
LEVEL_JITTER_P = 0.15   # chance a sub-manager lands one level off from the "needed" level


@dataclass
class Person:
    id: str
    function: str
    level: int
    title: str
    team: str | None
    manager_id: str | None


def sample_company_size(rng: random.Random, lo: int = 100, hi: int = 2000) -> int:
    """Skewed towards small companies: median ~270, a long tail up to `hi`."""
    return int(lo * (hi / lo) ** (rng.random() ** 1.6))


def _partition(n: int, k: int, rng: random.Random) -> list[int]:
    """Split n into k positive integers with uneven, random sizes."""
    k = max(1, min(k, n))
    weights = [rng.expovariate(1) + 0.3 for _ in range(k)]
    total = sum(weights)
    sizes = [1 + int((n - k) * w / total) for w in weights]
    for i in rng.sample(range(k), n - sum(sizes)):  # hand out the rounding remainder
        sizes[i] += 1
    return sizes


class _Company:
    def __init__(self, company_id: str, industry: str, size: int, rng: random.Random):
        self.company_id, self.industry, self.size, self.rng = company_id, industry, size, rng
        self.people: dict[str, Person] = {}
        self._leaf_team_pool: dict[str, list[str]] = {}  # per function, for leaf_teams functions

    # -- helpers ---------------------------------------------------------------
    def _add(self, function: str, level: int, title: str, team: str | None, manager_id: str | None) -> str:
        pid = f"{self.company_id}-{len(self.people):05d}"
        self.people[pid] = Person(pid, function, level, title, team, manager_id)
        return pid

    def _add_ic(self, fn: str, manager_id: str | None, team: str | None) -> str:
        f, rng = FUNCTIONS[fn], self.rng
        level = rng.choices(list(IC_LEVEL_WEIGHTS), weights=list(IC_LEVEL_WEIGHTS.values()))[0]
        role = rng.choices(f.ic_roles, weights=[1 / (i + 1) for i in range(len(f.ic_roles))])[0]
        if isinstance(role, tuple):
            title = role[level - SENIOR]
        else:
            title = {SENIOR: f"Senior {role}", MID: role,
                     JUNIOR: f"{rng.choice(['Junior', 'Graduate'])} {role}"}[level]
        return self._add(fn, level, title, team, manager_id)

    def _next_leaf_team(self, fn: str) -> str:
        """Unique unit names (stores, wards...) until they run out, then repeats."""
        pool = self._leaf_team_pool.get(fn)
        if not pool:
            pool = self._leaf_team_pool[fn] = self.rng.sample(FUNCTIONS[fn].teams, len(FUNCTIONS[fn].teams))
        return pool.pop()

    def _child_level(self, lower: list[int], group: int, span: tuple[int, int]) -> int:
        """Pick the management level for a sub-manager running `group` people.

        Small groups skip levels (a Head with 12 people manages Managers directly,
        no Senior Manager in between); big groups use the next level down.
        """
        avg = (span[0] + span[1]) / 2
        needed = max(1, math.ceil(math.log(group) / math.log(avg + 1)))
        i = max(0, len(lower) - needed)
        if self.rng.random() < LEVEL_JITTER_P:
            i = min(len(lower) - 1, max(0, i + self.rng.choice([-1, 1])))
        if i == len(lower) - 1 and group - 1 > span[1] and i > 0:
            i -= 1  # the lowest level would leave this group as one huge flat team
        return lower[i]

    # -- department subtrees ---------------------------------------------------
    def _build(self, fn: str, level: int, budget: int, manager_id: str | None, team: str | None,
               title: str | None = None) -> str:
        """Create a manager at `level` whose subtree (including them) has `budget` people."""
        f, rng = FUNCTIONS[fn], self.rng
        n = budget - 1
        lower = sorted(l for l in f.ladder if l > level)
        smin, smax = f.span
        is_leaf_manager = not lower or n <= smax
        if f.leaf_teams and is_leaf_manager and team is None:
            team = self._next_leaf_team(fn)
        if title is None:
            title = f.ladder[level]
            # Sub-department heads are always qualified in real life ("Head of Credit Risk",
            # not six peers called "Head of Risk"). Department tops (manager_id None) are not.
            if team and level <= HEAD and manager_id is not None:
                title = f"{title} - {team}"
        me = self._add(fn, level, title, team, manager_id)
        if is_leaf_manager:
            for _ in range(n):
                self._add_ic(fn, me, team)
            return me

        if rng.random() < DIRECT_IC_P:  # e.g. a Staff Engineer reporting straight to the Head
            for _ in range(rng.randint(1, 2)):
                self._add_ic(fn, me, team)
                n -= 1
        avg = (smin + smax) / 2
        k = max(2, min(smax, math.ceil(n / (avg + 1))))
        groups = _partition(n, k, rng)
        # A group bigger than its subtree can hold (given the levels left below) would end
        # up as one manager with 30+ direct reports. Split it, as real orgs do.
        cap = (smax + 1) ** len(lower)
        while max(groups) > cap:
            g = groups.pop(groups.index(max(groups)))
            groups += [g // 2, g - g // 2]
        teams = rng.sample(f.teams, len(f.teams))
        for i, g in enumerate(groups):
            # Teams are assigned at the first split under the department top and inherited
            # below (leaf_teams functions name the front-line unit instead). More subteams
            # than names means names repeat: deliberate ambiguity.
            child_team = team or (None if f.leaf_teams else teams[i % len(teams)])
            if g < 3:  # a "manager" of one person is rare; make them peers instead
                for _ in range(g):
                    self._add_ic(fn, me, child_team)
            else:
                self._build(fn, self._child_level(lower, g, f.span), g, me, child_team)
        return me

    def _top_level(self, fn: str, headcount: int) -> int:
        f, rng = FUNCTIONS[fn], self.rng
        emin = exec_min_size(self.industry, fn)
        if EXEC in f.ladder and emin is not None and self.size >= emin * rng.uniform(0.75, 1.25):
            return EXEC
        if VP in f.ladder and headcount >= 150:
            desired = VP
        elif headcount <= 5 and rng.random() < 0.5:
            desired = MGR
        else:
            desired = HEAD
        options = [l for l in sorted(f.ladder) if l >= desired and l > EXEC]
        return options[0] if options else max(f.ladder)

    def _allocate(self, budget: int) -> dict[str, int]:
        """Headcount per function, with noise; tiny functions may not exist at all."""
        rng = self.rng
        weights = {fn: s * rng.uniform(0.7, 1.3) for fn, s in INDUSTRIES[self.industry].functions.items()}
        total = sum(weights.values())
        expected = {fn: w / total * budget for fn, w in weights.items()}
        kept = {fn: e for fn, e in expected.items() if e >= 1 or rng.random() < e}
        scale = budget / sum(kept.values())
        raw = {fn: max(1.0, e * scale) for fn, e in kept.items()}
        alloc = {fn: int(v) for fn, v in raw.items()}
        # Largest-remainder rounding so the total is exact.
        for fn in sorted(raw, key=lambda fn: raw[fn] - alloc[fn], reverse=True)[: budget - sum(alloc.values())]:
            alloc[fn] += 1
        while sum(alloc.values()) > budget:  # only possible when many tiny functions got bumped to 1
            alloc[max(alloc, key=alloc.get)] -= 1
        return alloc

    # -- whole company -----------------------------------------------------------
    def build(self) -> list[Person]:
        rng, ind = self.rng, INDUSTRIES[self.industry]
        ceo_title = rng.choices(list(ind.ceo_titles), weights=list(ind.ceo_titles.values()))[0]
        ceo = self._add(EXEC_OFFICE, CEO, ceo_title, None, None)
        specials = 1 + (self.size >= 800 and rng.random() < 0.5)  # EA to CEO, maybe a Chief of Staff
        alloc = self._allocate(self.size - 1 - specials)

        tops: dict[str, str] = {}
        for fn, h in alloc.items():
            f = FUNCTIONS[fn]
            if f.multi_head:  # e.g. Partners, each running a practice, all under the Managing Partner
                top = min(f.ladder)
                for g in _partition(h, max(1, round(h / 25)), rng):
                    self._build(fn, top, g, ceo, None) if g > 1 else self._add_ic(fn, ceo, None)
                continue
            if h == 1:  # a lone specialist, e.g. the company's only Legal Counsel
                tops[fn] = self._add_ic(fn, None, None)
                continue
            level = self._top_level(fn, h)
            title = None
            if f.big_head_title and level == HEAD and self.size >= f.big_head_title[0]:
                title = f.big_head_title[1]
            tops[fn] = self._build(fn, level, h, None, None, title)

        self._attach_heads(tops, ceo)
        self._add_ic_specials(ceo, specials)
        return list(self.people.values())

    def _attach_heads(self, tops: dict[str, str], ceo: str) -> None:
        """Wire each department head to their manager, resolving dependencies in order."""
        rng, people = self.rng, self.people
        targets = {}
        for fn, pid in tops.items():
            dist = head_reports_to(self.industry, fn)
            targets[fn] = "ceo" if people[pid].level == EXEC else rng.choices(list(dist), weights=list(dist.values()))[0]

        def attach(fn: str) -> None:
            me = people[tops[fn]]
            if me.manager_id is not None:
                return
            t = targets[fn]
            if t == "ceo" or t not in tops:
                me.manager_id = ceo
                return
            attach(t)
            boss = people[tops[t]]
            # Never report to someone more junior: walk up the target's chain.
            while boss.level >= me.level and boss.manager_id is not None:
                boss = people[boss.manager_id]
            me.manager_id = boss.id

        for fn in tops:
            attach(fn)

    def _add_ic_specials(self, ceo: str, specials: int) -> None:
        rng = self.rng
        self._add(EXEC_OFFICE, MID, "Executive Assistant to the CEO", None, ceo)
        if specials == 2:
            self._add(EXEC_OFFICE, HEAD, "Chief of Staff", None, ceo)
        if self.size >= 1000:  # some C-suite execs get their own EA (adds to headcount)
            for p in [p for p in self.people.values() if p.level == EXEC]:
                if rng.random() < 0.4:
                    self._add(EXEC_OFFICE, MID, "Executive Assistant", None, p.id)


def build_company(company_id: str, industry: str, size: int, rng: random.Random) -> list[Person]:
    return _Company(company_id, industry, size, rng).build()


# -- review output ---------------------------------------------------------------------
def render(people: list[Person], max_depth: int = 3) -> str:
    """Managers as an indented tree; ICs collapsed into a count per manager."""
    by_id = {p.id: p for p in people}
    kids: dict[str | None, list[Person]] = {}
    for p in people:
        kids.setdefault(p.manager_id, []).append(p)

    def subtree(pid: str) -> int:
        return 1 + sum(subtree(c.id) for c in kids.get(pid, []))

    lines = []

    def walk(p: Person, depth: int) -> None:
        children = kids.get(p.id, [])
        managers = sorted([c for c in children if c.id in kids], key=lambda c: (c.level, -subtree(c.id)))
        ics = len(children) - len(managers)
        team = f" [{p.team}]" if p.team else ""
        note = f"  ({subtree(p.id) - 1} below" + (f", {ics} direct ICs" if ics else "") + ")" if children else ""
        lines.append(f"{'    ' * depth}{p.title}{team}{note}")
        if depth < max_depth:
            for c in managers:
                walk(c, depth + 1)
        elif managers:
            lines.append(f"{'    ' * (depth + 1)}... {len(managers)} more managers")

    walk(next(p for p in people if p.manager_id is None), 0)
    assert all(p.manager_id is None or p.manager_id in by_id for p in people)
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    rng = random.Random(7)
    samples = [("saas", 180), ("financial_services", 1400), ("retail", 600)]
    if len(sys.argv) == 3:
        samples = [(sys.argv[1], int(sys.argv[2]))]
    for industry, size in samples:
        people = build_company("demo", industry, size, rng)
        print(f"\n===== {INDUSTRIES[industry].label}, target {size} staff, actual {len(people)} =====")
        levels = {}
        for p in people:
            levels[LEVEL_NAMES[p.level]] = levels.get(LEVEL_NAMES[p.level], 0) + 1
        print("Levels:", ", ".join(f"{k} {v}" for k, v in levels.items()))
        print(render(people, max_depth=3))
