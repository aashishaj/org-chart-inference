"""Gemini fallback for titles the rules can't read confidently.

Gemini sees only what's public: the raw title and the company's industry. It may
answer "can't tell" (null), which we prefer to a confident guess. Answers are
validated and saved to llm_titles.json (committed), so the app never needs a key.

Also parses a random sample of titles the rules *were* confident about: comparing
the two on that sample is an independent check on the rule parser, which was
written by someone who had seen the generator's spellings.

    uv run python -m orgchart.inference.llm_titles      # build llm_titles.json
"""

import json
import random
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

from .. import llm
from .data import load_companies
from .titles import ParsedTitle, parse_title

PARSES_PATH = Path(__file__).with_name("llm_titles.json")
ROUTE_BELOW = 0.7       # rule confidence under which Gemini is consulted
BATCH = 150
CHECK_SAMPLE = 1500

DEPARTMENTS = {
    "executive": "CEO, managing director, founder, chief of staff, executive assistants",
    "engineering": "software engineering, developers, QA, DevOps, CTO",
    "product": "product managers, product owners, business analysts",
    "design": "UX/UI and product design, user research",
    "data": "data, analytics, BI, data science, machine learning",
    "security": "information / cyber security, CISO",
    "it": "internal IT, service desk, systems, networks, CIO",
    "sales": "sales, account executives and managers, business development, CRO",
    "marketing": "marketing, brand, content, growth, communications",
    "customer_success": "customer success, onboarding, implementation",
    "support": "customer support and service, contact centre",
    "finance": "finance, accounting, payroll, FP&A, CFO",
    "hr": "HR, people & culture, recruitment, talent",
    "legal": "legal, counsel, company secretary",
    "operations": "general business operations, facilities, procurement, COO",
    "risk": "risk management (banking/finance)",
    "compliance": "compliance, AML, financial crime",
    "lending": "banking and lending: relationship managers, credit, loans",
    "clinical": "nurses, doctors, allied health, pharmacists",
    "hse": "health, safety and environment",
    "mining_ops": "mine site operations: operators, fitters, geologists, superintendents",
    "projects": "construction projects: project managers, site engineers, estimators",
    "production": "factory production: operators, shift supervisors, plant managers",
    "quality": "quality assurance / control (not software QA)",
    "supply_chain": "supply chain, logistics planning, procurement, demand planning",
    "warehouse_ops": "warehouses and distribution centres",
    "transport": "drivers, fleet, dispatch",
    "store_ops": "retail stores: store managers, retail assistants, area managers",
    "merchandising": "retail buying and merchandise planning",
    "consulting": "client-facing professional services: partners, consultants, auditors",
    "academic": "lecturers, tutors, researchers, deans",
    "student_services": "admissions, enrolment, student support",
}
LEVELS = """0 CEO / managing director / managing partner / vice-chancellor
1 C-suite (CFO, CTO, COO, Chief X Officer, General Counsel)
2 VP / general manager / partner / dean
3 Head of X / director
4 senior manager / area manager / superintendent
5 manager / team lead / supervisor (manages people)
6 senior individual contributor (senior, principal, staff, clinical nurse)
7 individual contributor (includes manager-titled ICs like Product Manager, Account Manager)
8 junior / graduate / intern / trainee"""

PROMPT = """You are parsing job titles from a messy Australian company database.

For each item, return its seniority level and department.

Seniority levels:
{levels}

Departments (use exactly one key, or null):
{departments}

Rules:
- Use the company's industry to resolve ambiguous titles ("Consultant" at a consulting firm is client
  services; "Shift Supervisor" at a miner is mining_ops).
- Ignore taglines, emojis, company names and team names.
- If the title genuinely doesn't say (e.g. "Team Member", "Staff"), return null for that field.
  A null is better than a guess.
- contractor: true if the title says contract, contractor, fixed term or via an agency.
- confidence: 0 to 1, how sure you are of BOTH fields.

Items (JSON):
{items}

Return a JSON list with one object per item, in the same order:
[{{"id": <id>, "level": <0-8 or null>, "department": <key or null>, "contractor": <bool>, "confidence": <0-1>}}]"""


@dataclass(frozen=True)
class GeminiParse:
    level: int | None
    department: str | None
    contractor: bool
    confidence: float


def _validate(item: dict) -> GeminiParse | None:
    try:
        level = item.get("level")
        level = int(level) if level is not None and 0 <= int(level) <= 8 else None
        dept = item.get("department")
        dept = dept if dept in DEPARTMENTS else None
        conf = float(item.get("confidence") or 0)
        return GeminiParse(level, dept, bool(item.get("contractor")), max(0.0, min(1.0, conf)))
    except (TypeError, ValueError):
        return None


def ask_gemini(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], GeminiParse]:
    """Parse (title, industry) pairs in deterministic batches (so reruns hit the cache)."""
    out = {}
    pairs = sorted(set(pairs))
    levels = LEVELS
    departments = "\n".join(f"- {k}: {v}" for k, v in DEPARTMENTS.items())
    for i in range(0, len(pairs), BATCH):
        batch = pairs[i:i + BATCH]
        items = [{"id": j, "title": t, "industry": ind} for j, (t, ind) in enumerate(batch)]
        print(f"  gemini batch {i // BATCH + 1}/{-(-len(pairs) // BATCH)}", flush=True)
        try:
            answer = llm.ask_json(PROMPT.format(levels=levels, departments=departments, items=json.dumps(items)))
        except Exception as e:  # one bad batch shouldn't sink the run; those titles keep the rule parse
            print(f"    batch failed: {str(e)[:120]}")
            continue
        for a in answer if isinstance(answer, list) else []:
            if isinstance(a, dict) and isinstance(a.get("id"), int) and 0 <= a["id"] < len(batch):
                if parsed := _validate(a):
                    out[batch[a["id"]]] = parsed
    return out


def build() -> dict:
    companies = load_companies()
    routed, confident = set(), set()
    for c in companies.values():
        for r in c.records:
            if not r.title:
                continue
            (routed if parse_title(r.title, c.industry).confidence < ROUTE_BELOW else confident).add((r.title, c.industry))
    check = set(random.Random(7).sample(sorted(confident), CHECK_SAMPLE))
    answers = ask_gemini(sorted(routed | check))
    data = {
        "models": sorted(llm.models_used), "route_below": ROUTE_BELOW,
        "parses": [{"title": t, "industry": ind, "level": g.level, "department": g.department,
                    "contractor": g.contractor, "confidence": g.confidence, "check_sample": (t, ind) in check}
                   for (t, ind), g in sorted(answers.items())],
    }
    PARSES_PATH.write_text(json.dumps(data, indent=0, ensure_ascii=False) + "\n")
    print(f"routed {len(routed):,} + check sample {len(check):,}; answered {len(answers):,}")
    return data


@cache
def _parses() -> dict[tuple[str, str], GeminiParse]:
    if not PARSES_PATH.exists():
        return {}
    data = json.loads(PARSES_PATH.read_text())
    return {(p["title"], p["industry"]): GeminiParse(p["level"], p["department"], p["contractor"], p["confidence"])
            for p in data["parses"]}


def gemini_parse(title: str, industry: str) -> GeminiParse | None:
    return _parses().get((title, industry))


def parse_title_hybrid(title: str, industry: str = "") -> ParsedTitle:
    """Rules when they're confident; Gemini for the rest, field by field."""
    rule = parse_title(title, industry)
    if rule.confidence >= ROUTE_BELOW or not (g := gemini_parse(title, industry)):
        return rule
    flags = set(rule.flags) | ({"contractor"} if g.contractor else set())
    level, level_conf = rule.level, rule.level_conf
    if g.level is not None and g.confidence > level_conf:
        level, level_conf = g.level, g.confidence
    function, function_conf = rule.function, rule.function_conf
    # For a vague title ("Analyst") the industry default (consulting at a consulting firm)
    # beats Gemini's guess at a department the title never names.
    keep_industry_default = "vague" in rule.flags and rule.function is not None
    if g.department is not None and g.confidence > function_conf and not keep_industry_default:
        function, function_conf = g.department, g.confidence
    return replace(rule, level=level, level_conf=level_conf, function=function, function_conf=function_conf,
                   flags=frozenset(flags | {"gemini"}), rule=f"gemini (rules: {rule.rule or 'none'})")


if __name__ == "__main__":
    build()
