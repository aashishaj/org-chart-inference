"""The mess layer, part 1: mess profiles and the title renderer.

Turns a person's clean canonical title into the messy string a data provider would
actually hold, and records a tag for every kind of mess applied. Tags go into the
answer key so accuracy can be broken down by mess type later.

The renderer never touches the true structure: stale titles and title inflation
change what the title *says*, not who reports to whom.

Run `uv run python -m orgchart.generator.mess` for before/after samples.
"""

import random
from dataclasses import dataclass, field

from .builder import EXEC_OFFICE, Person
from .clues import ClueConfig
from .templates import EXEC, FUNCTIONS, JUNIOR, MGR, MID, SENIOR

# -- profiles --------------------------------------------------------------------------


@dataclass(frozen=True)
class MessProfile:
    name: str
    share: float              # share of companies at this level
    vocab_variant: float      # use a real-world spelling instead of the canonical title
    seniority_format: float   # "Sr." / "Snr" / "(Senior)" instead of "Senior"
    acting: float             # "Acting" / "Interim" / "A/" on a manager
    stale: float              # manager whose profile still shows their pre-promotion title
    inflate_company: float    # chance a small company inflates its titles at all
    vague: float              # "Manager", "Team Member", ...
    creative: float           # "Code Ninja", "Chief Happiness Officer" (startups only)
    fluff: float              # LinkedIn taglines, "@ Company", emojis
    casing: float             # ALL CAPS / lowercase
    typo: float
    clues: ClueConfig = field(default_factory=ClueConfig)


PROFILES = {
    "clean": MessProfile("clean", .20, vocab_variant=.25, seniority_format=.15, acting=.005, stale=.02,
                         inflate_company=.10, vague=0, creative=0, fluff=.01, casing=.005, typo=0),
    "medium": MessProfile("medium", .50, vocab_variant=.55, seniority_format=.45, acting=.01, stale=.05,
                          inflate_company=.30, vague=.03, creative=.01, fluff=.06, casing=.03, typo=.015,
                          clues=ClueConfig(colocate=.75, joined_after=.82, burst=.30, prev_known=.65,
                                           follow_manager=.12, team_in_title_mgr=.45, team_in_title_ic=.25)),
    "messy": MessProfile("messy", .30, vocab_variant=.80, seniority_format=.70, acting=.02, stale=.10,
                         inflate_company=.50, vague=.08, creative=.03, fluff=.12, casing=.08, typo=.05,
                         clues=ClueConfig(colocate=.65, joined_after=.75, burst=.25, prev_known=.55,
                                          follow_manager=.10, team_in_title_mgr=.30, team_in_title_ic=.15)),
}


def pick_profile(rng: random.Random) -> MessProfile:
    return rng.choices(list(PROFILES.values()), weights=[p.share for p in PROFILES.values()])[0]


# -- word lists ----------------------------------------------------------------------------
SENIORITY_FORMATS = {
    "Senior": ["Senior {r}", "Sr. {r}", "Sr {r}", "Snr {r}", "{r} (Senior)", "{r}, Senior", "{r} III"],
    "Junior": ["Junior {r}", "Jr. {r}", "Jnr {r}", "{r} I", "{r} (Junior)"],
    "Graduate": ["Graduate {r}", "Grad {r}", "{r} (Graduate)", "{r} - Graduate Program"],
}
TEAM_FORMATS = {"{t} - {team}": 6, "{t}, {team}": 4, "{t} ({team})": 3, "{t} | {team}": 2, "{t} – {team}": 2,
                "{team} {t}": 1}  # "Payments Engineer" style: real, but rare
ACTING = ["Acting {t}", "Interim {t}", "A/{t}", "{t} (Acting)", "{t} (Interim)"]
FLUFF = [" | Building high-performing teams", " @ {company}", " | Ex-{prev}", " 🚀", " | Hiring!",
         " | Helping businesses grow", " | Speaker & Mentor", " ✨", " | Passionate about people",
         " at {company}", " | Open to opportunities"]
VAGUE_MANAGER = ["Manager", "Team Leader", "Director", "Leader", "Management"]
VAGUE_IC = ["Consultant", "Team Member", "Staff", "Specialist", "Associate", "Analyst", "Employee"]
CREATIVE = {  # function -> playful titles real startups use
    "engineering": ["Code Ninja", "Software Craftsperson", "Engineering Wizard", "Developer Advocate"],
    "marketing": ["Growth Hacker", "Brand Storyteller", "Chief Storyteller"],
    "customer_success": ["Customer Champion", "Customer Happiness Hero"],
    "support": ["Customer Happiness Hero", "Support Ninja"],
    "hr": ["Chief Happiness Officer", "Head of Happiness", "People Ninja"],
    "sales": ["Deal Closer", "Revenue Rockstar"],
    "design": ["Pixel Pusher", "Design Wizard"],
    "data": ["Data Wrangler", "Data Ninja"],
}
CREATIVE_INDUSTRIES = {"saas"}
_PREFIXES = ("Senior ", "Junior ", "Graduate ")


@dataclass
class TitleContext:
    profile: MessProfile
    vocab: dict[str, list[str]]
    company_name: str
    industry: str
    inflated: bool            # this company inflates titles
    is_manager: bool          # has direct reports in the true tree


# -- helpers ---------------------------------------------------------------------------------
def _split(title: str, team: str | None, vocab: dict) -> tuple[str | None, str, bool]:
    """canonical title -> (seniority prefix or None, core title, team baked into title)."""
    baked = bool(team) and title.endswith(f" - {team}")
    if baked:
        title = title[: -len(f" - {team}")]
    if title in vocab:
        return None, title, baked
    for pre in _PREFIXES:
        if title.startswith(pre) and title[len(pre):] in vocab:
            return pre.strip(), title[len(pre):], baked
    return None, title, baked


def _ladder_neighbour(p: Person, step: int) -> str | None:
    """A manager's title one rung up (step=-1) or down (step=+1) their job ladder."""
    if p.function == EXEC_OFFICE or p.level >= SENIOR:
        return None
    f = FUNCTIONS[p.function]
    levels = sorted(f.ladder)
    if p.level not in levels:
        return None
    i = levels.index(p.level) + step
    if 0 <= i < len(levels):
        return f.ladder[levels[i]]
    if step > 0 and p.level == MGR:  # a new manager's previous job: a senior IC
        role = next((r for r in f.ic_roles if isinstance(r, str)), None)
        return f"Senior {role}" if role else None
    return None


def _typo(s: str, rng: random.Random) -> str:
    words = [i for i, w in enumerate(s.split(" ")) if len(w) > 4 and w.isalpha()]
    if not words:
        return s
    parts = s.split(" ")
    w = parts[i := rng.choice(words)]
    j = rng.randrange(1, len(w) - 1)
    kind = rng.random()
    if kind < 0.4:
        w = w[:j] + w[j + 1] + w[j] + w[j + 2:]   # swap
    elif kind < 0.7:
        w = w[:j] + w[j + 1:]                       # drop
    else:
        w = w[:j] + w[j] + w[j:]                    # double
    parts[i] = w
    return " ".join(parts)


# -- the renderer --------------------------------------------------------------------------------
def render_title(p: Person, ctx: TitleContext, rng: random.Random) -> tuple[str, list[str]]:
    """Return (messy title, mess tags). Does not modify p."""
    prof, tags = ctx.profile, []
    prefix, core, team_baked = _split(p.title, p.team, ctx.vocab)

    # 1. Stale or inflated: the title says something other than the person's real level.
    if ctx.is_manager and p.level > EXEC and rng.random() < prof.stale:
        old = _ladder_neighbour(p, +1)
        if old:
            prefix, core, _ = _split(old, None, ctx.vocab)
            tags.append("stale")
    elif ctx.inflated and p.level > EXEC and rng.random() < (0.6 if ctx.is_manager else 0.3):
        if p.level >= SENIOR:  # ICs inflate within their own role: Junior -> plain, plain -> Senior
            new_prefix = {MID: "Senior", JUNIOR: None}.get(p.level, prefix)
            if new_prefix != prefix:
                prefix = new_prefix
                tags.append("inflated")
        elif up := _ladder_neighbour(p, -1):
            prefix, core, _ = _split(up, None, ctx.vocab)
            tags.append("inflated")

    # 2. Vague or creative titles replace everything else.
    creative = CREATIVE.get(p.function) if ctx.industry in CREATIVE_INDUSTRIES else None
    if creative and rng.random() < prof.creative:
        title = rng.choice(creative)
        tags.append("creative")
    elif p.level > EXEC and rng.random() < prof.vague:
        title = rng.choice(VAGUE_MANAGER if ctx.is_manager else VAGUE_IC)
        tags.append("vague")
    else:
        # 3. Real-world spelling of the core title.
        if core in ctx.vocab and ctx.vocab[core] and rng.random() < prof.vocab_variant:
            # Long tail: Gemini lists the most common spellings first, so weight by rank
            # ("Engineering Mgr" should be far more common than "Systems Engineering Manager").
            variants = ctx.vocab[core]
            core = rng.choices(variants, weights=[1 / (i + 1) for i in range(len(variants))])[0]
            tags.append("variant")
        # 4. Seniority prefix, written one of several ways.
        if prefix:
            if rng.random() < prof.seniority_format:
                fmt = rng.choice(SENIORITY_FORMATS[prefix][1:])
                tags.append("seniority_format")
            else:
                fmt = SENIORITY_FORMATS[prefix][0]
            title = fmt.format(r=core)
        else:
            title = core
        # 5. Team name: always on sub-head titles, otherwise when the clue says so.
        if p.team and (team_baked or p.show_team):
            fmt = rng.choices(list(TEAM_FORMATS), weights=list(TEAM_FORMATS.values()))[0]
            title = fmt.format(t=title, team=p.team)
            tags.append("team")
        # 6. Acting / interim managers.
        if ctx.is_manager and p.level > EXEC and rng.random() < prof.acting:
            title = rng.choice(ACTING).format(t=title)
            tags.append("acting")

    # 7. LinkedIn fluff.
    if rng.random() < prof.fluff:
        options = [f for f in FLUFF if "{prev}" not in f or p.prev_employer]
        title += rng.choice(options).format(company=ctx.company_name, prev=p.prev_employer)
        tags.append("fluff")

    # 8. Surface noise.
    if rng.random() < prof.typo:
        title = _typo(title, rng)
        tags.append("typo")
    if rng.random() < prof.casing:
        title = title.upper() if rng.random() < 0.6 else title.lower()
        tags.append("casing")
    return title, tags


if __name__ == "__main__":
    from .builder import build_company
    from .clues import add_clues, make_employer_pool
    from .vocabulary import load

    vocab, rng = load(), random.Random(11)
    pool = make_employer_pool(rng)
    for level, industry, size in [("clean", "financial_services", 900), ("medium", "saas", 250), ("messy", "saas", 180),
                                  ("messy", "healthcare", 600)]:
        prof = PROFILES[level]
        people = build_company("demo", industry, size, rng)
        add_clues(people, industry, size, rng, pool, prof.clues)
        managers = {p.manager_id for p in people}
        inflated = size < 300 and rng.random() < prof.inflate_company
        print(f"\n===== {level.upper()} | {industry} | {size} staff | inflates titles: {inflated} =====")
        sample = rng.sample(people, 16)
        for p in sorted(sample, key=lambda p: p.level):
            ctx = TitleContext(prof, vocab, "Bluegum Labs", industry, inflated, p.id in managers)
            t, tags = render_title(p, ctx, rng)
            print(f"  {p.title:<42} -> {t:<52} {','.join(tags)}")
