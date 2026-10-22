"""Hidden clues: extra fields on each person that correlate with who their real
manager is. Each clue has a reliability dial (ClueConfig) so we can later measure
how much inference depends on it, and turn it down for messy companies.

- location:      people mostly sit in their manager's office
- start_date:    people mostly join after their manager, often in hiring bursts
- prev_employer: some people followed their manager from a previous company
- show_team:     whether the team name is visible in the person's title
"""

import random
from dataclasses import dataclass

from .builder import Person
from .templates import CEO

TODAY = 2026 + 9 / 12  # Oct 2026, as a fractional year


@dataclass(frozen=True)
class ClueConfig:
    colocate: float = 0.80            # same office as manager
    joined_after: float = 0.85        # started after manager (includes bursts)
    burst: float = 0.35               # started within 6 months of manager
    prev_known: float = 0.75          # previous employer is listed at all
    follow_manager: float = 0.15      # followed manager from their previous employer
    team_in_title_mgr: float = 0.60
    team_in_title_ic: float = 0.35


# -- geography -----------------------------------------------------------------------
AU_CITIES = {"Sydney": .38, "Melbourne": .32, "Brisbane": .12, "Perth": .08, "Adelaide": .05,
             "Canberra": .03, "Hobart": .02}
OVERSEAS = ["Auckland", "Singapore", "London", "San Francisco", "New York", "Manila", "Bangalore"]
HQ_OVERRIDES = {"mining": {"Perth": .6, "Brisbane": .3, "Melbourne": .1},
                "education": {"Melbourne": .3, "Sydney": .3, "Brisbane": .15, "Adelaide": .1, "Perth": .1,
                              "Canberra": .05}}
GLOBAL_P = {"saas": .30, "professional_services": .25, "mining": .20, "financial_services": .15}  # else .08

# Teams that pin people to a place: sales regions, stores, DCs, projects.
TEAM_CITY = {
    "NSW": "Sydney", "VIC": "Melbourne", "QLD": "Brisbane", "WA": "Perth", "New Zealand": "Auckland",
    "APAC": "Singapore",
    "Eastern Creek DC": "Sydney", "Truganina DC": "Melbourne", "Brisbane DC": "Brisbane", "Perth DC": "Perth",
    "Adelaide DC": "Adelaide",
    "Western Sydney Airport": "Sydney", "Metro Tunnel": "Melbourne", "Cross River Rail": "Brisbane",
    "Sydney Metro West": "Sydney", "Inland Rail": "Toowoomba", "North East Link": "Melbourne",
    "WestConnex": "Sydney", "Snowy 2.0": "Cooma", "Brisbane Olympic Venues": "Brisbane", "Perth METRONET": "Perth",
}
_STORES = {
    "Sydney": ["Bondi Junction", "Westfield Sydney", "Macquarie Centre", "Parramatta", "Miranda", "Castle Hill",
               "Burwood", "Chatswood", "Penrith", "Liverpool"],
    "Melbourne": ["Chadstone", "Highpoint", "Doncaster", "Southland", "Fountain Gate", "Knox", "Eastland",
                  "Northland", "Melbourne Central", "Emporium", "Watergardens"],
    "Brisbane": ["Carindale", "Indooroopilly", "Chermside"], "Gold Coast": ["Robina", "Pacific Fair"],
    "Perth": ["Garden City", "Karrinyup", "Booragoon", "Joondalup"], "Adelaide": ["Marion", "Tea Tree Plaza", "Rundle Mall"],
    "Canberra": ["Canberra Centre", "Belconnen"], "Hobart": ["Hobart CBD"],
}
TEAM_CITY |= {store: city for city, stores in _STORES.items() for store in stores}

# Functions whose branches run at a remote site rather than an office.
SITES = {
    "mining_ops": ["Karratha", "Port Hedland", "Newman", "Kalgoorlie", "Mount Isa", "Moranbah", "Emerald",
                   "Olympic Dam"],
    "production": ["Dandenong", "Wetherill Park", "Geelong", "Wacol", "Kwinana", "Smithfield"],
}


def _pick(rng: random.Random, dist: dict[str, float]) -> str:
    return rng.choices(list(dist), weights=list(dist.values()))[0]


def company_offices(rng: random.Random, industry: str, size: int) -> list[str]:
    """HQ first, then more AU offices as the company grows, maybe overseas offices."""
    hq = _pick(rng, HQ_OVERRIDES.get(industry, AU_CITIES))
    others = [c for c in AU_CITIES if c != hq]
    n_au = min(len(others), int(size / 350) + (rng.random() < 0.5))
    offices = [hq] + rng.sample(others, n_au)
    if size >= 300 and rng.random() < GLOBAL_P.get(industry, .08):
        offices += rng.sample(OVERSEAS, rng.randint(1, 1 + size // 700))
    return offices


def _office_weights(offices: list[str]) -> dict[str, float]:
    """Where someone lands when they're *not* with their manager: mostly HQ, some
    other AU offices, rarely overseas."""
    au = [o for o in offices[1:] if o not in OVERSEAS]
    w = {offices[0]: 0.6}
    w |= {o: 0.35 / len(au) for o in au}
    w |= {o: 0.05 for o in offices[1:] if o in OVERSEAS}
    return w


# -- previous employers ------------------------------------------------------------------
_NAME_A = ["Harbour", "Southern Cross", "Pacific", "Bluegum", "Coastal", "Ironbark", "Summit", "Meridian",
           "Kestrel", "Wattle", "Redgum", "Northstar", "Banksia", "Granite", "Silverleaf", "Tasman", "Eureka",
           "Outback", "Coral", "Highland", "Riverbend", "Sterling", "Lighthouse", "Arcadia", "Brightwater"]
_NAME_B = ["Group", "Partners", "Technologies", "Holdings", "Health", "Logistics", "Capital", "Retail",
           "Resources", "Consulting", "Labs", "Systems", "Industries", "Bank", "Energy", "Solutions"]


def make_employer_pool(rng: random.Random, n: int = 2500) -> list[str]:
    """Plausible fictional employer names. Order matters: earlier = bigger employer."""
    names = {f"{a} {b}" for a in _NAME_A for b in _NAME_B}
    names |= {f"{a} {b} {c}" for a in _NAME_A for b in _NAME_A if a != b for c in ("Group", "Co", "Pty Ltd")}
    pool = sorted(names)
    rng.shuffle(pool)
    return pool[:n]


def _zipf_pick(rng: random.Random, pool: list[str]) -> str:
    """A few employers are very common (like the big four banks), most are rare."""
    i = int(len(pool) * rng.random() ** 3)
    return pool[min(i, len(pool) - 1)]


# -- dates -----------------------------------------------------------------------------
def _fmt(year: float) -> str:
    y = int(year)
    return f"{y}-{int((year - y) * 12) + 1:02d}"


def _founded(rng: random.Random, industry: str, size: int) -> float:
    if industry == "saas":
        return rng.uniform(2004, 2021 - size / 400)
    return rng.uniform(1950, 2018 - size / 200)


# -- main ------------------------------------------------------------------------------
def add_clues(people: list[Person], industry: str, size: int, rng: random.Random,
              employer_pool: list[str], cfg: ClueConfig = ClueConfig()) -> dict:
    """Fill in clue fields in place. Returns company-level facts (offices, founded year)."""
    offices = company_offices(rng, industry, size)
    founded = _founded(rng, industry, size)
    kids: dict[str, list[Person]] = {}
    for p in people:
        if p.manager_id:
            kids.setdefault(p.manager_id, []).append(p)
    start: dict[str, float] = {}
    office_w = _office_weights(offices)

    def place(p: Person, boss: Person | None) -> None:
        if p.team in TEAM_CITY:
            p.location = TEAM_CITY[p.team]
        elif p.function in SITES and boss is not None and boss.function != p.function:
            p.location = offices[0]  # the department top sits at HQ...
        elif p.function in SITES and boss is not None and boss.location not in SITES[p.function]:
            p.location = rng.choice(SITES[p.function])  # ...each branch below runs a site
        elif boss is None:
            p.location = offices[0]
        elif rng.random() < cfg.colocate:
            p.location = boss.location
        else:
            p.location = _pick(rng, office_w)

    def date(p: Person, boss: Person | None) -> None:
        if boss is None:
            founder = "Founder" in p.title or rng.random() < 0.3
            s = founded if founder else max(founded, TODAY - rng.expovariate(1 / 6))
        else:
            m, r = start[boss.id], rng.random()
            if r < cfg.burst:
                s = m + rng.uniform(0, 0.5)
            elif r < cfg.joined_after:
                s = m + (TODAY - m) * rng.betavariate(1, 2)
            else:
                s = founded + (m - founded) * rng.random()  # was here before this manager arrived
        start[p.id] = s = min(max(s, founded), TODAY - 1 / 12)
        p.start_date = _fmt(s)

    def employer(p: Person, boss: Person | None) -> None:
        if rng.random() >= cfg.prev_known:
            return
        followed = (boss is not None and boss.prev_employer and start[p.id] > start[boss.id]
                    and boss.level > CEO and rng.random() < cfg.follow_manager)
        p.prev_employer = boss.prev_employer if followed else _zipf_pick(rng, employer_pool)

    root = next(p for p in people if p.manager_id is None)
    stack = [(root, None)]
    while stack:  # top-down, so every manager is done before their reports
        p, boss = stack.pop()
        place(p, boss)
        date(p, boss)
        employer(p, boss)
        if p.team:
            p.show_team = rng.random() < (cfg.team_in_title_mgr if p.id in kids else cfg.team_in_title_ic)
        stack.extend((c, p) for c in kids.get(p.id, []))
    return {"offices": offices, "founded": int(founded)}
