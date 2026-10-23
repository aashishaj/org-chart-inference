"""The mess layer, part 2: every field other than the title.

Rule: noise must stay *recoverable*. "Greater Sydney Area", "Sydney NSW" and
"Sydney, New South Wales, Australia" all decode back to Sydney; "Mar 2021" and
"03/2021" back to 2021-03. Mess should make inference work for a clue, not
destroy it. Blanks, "Remote" and wrong departments are the deliberate exceptions,
and they're tagged.

Run `uv run python -m orgchart.generator.fields` for sample rows.
"""

import random
from dataclasses import dataclass

from faker import Faker

from .builder import EXEC_OFFICE, Person
from .templates import FUNCTIONS


@dataclass(frozen=True)
class FieldRates:
    title_missing: float
    dept_missing: float
    dept_synonym: float     # "Eng" / "R&D" instead of "Engineering"
    dept_leak: float        # department shows the reporting line's function (cost centre)
    dept_wrong: float       # just wrong
    loc_missing: float
    remote: float
    date_missing: float
    year_only: float
    format_mess: float      # non-standard location / date / name format
    name_format: float


FIELD_RATES = {
    "clean": FieldRates(title_missing=.01, dept_missing=.20, dept_synonym=.25, dept_leak=.20, dept_wrong=.01,
                        loc_missing=.03, remote=.02, date_missing=.05, year_only=.03, format_mess=.15,
                        name_format=.05),
    "medium": FieldRates(title_missing=.04, dept_missing=.40, dept_synonym=.50, dept_leak=.25, dept_wrong=.03,
                         loc_missing=.10, remote=.04, date_missing=.15, year_only=.10, format_mess=.45,
                         name_format=.15),
    "messy": FieldRates(title_missing=.08, dept_missing=.60, dept_synonym=.70, dept_leak=.30, dept_wrong=.06,
                        loc_missing=.20, remote=.07, date_missing=.30, year_only=.20, format_mess=.75,
                        name_format=.30),
}

# -- departments ----------------------------------------------------------------------------
DEPT_SYNONYMS = {
    "engineering": ["Eng", "R&D", "Technology", "Product & Engineering", "Tech", "Software Development"],
    "product": ["Product Management", "Product & Engineering", "Prod"],
    "design": ["UX", "Product Design", "Design & Research"],
    "data": ["Data & Analytics", "Analytics", "BI", "Insights", "Data Science"],
    "security": ["Cyber Security", "InfoSec", "Information Security", "Cyber"],
    "it": ["Information Technology", "Technology", "ICT", "IT Services"],
    "sales": ["Sales & BD", "Business Development", "Commercial", "Revenue"],
    "marketing": ["Mktg", "Marketing & Comms", "Brand & Marketing", "Growth"],
    "customer_success": ["CS", "Client Success", "Customer Experience", "CX"],
    "support": ["Customer Service", "Customer Care", "Contact Centre", "Service Desk"],
    "finance": ["Accounting", "Finance & Accounting", "Fin", "Treasury"],
    "hr": ["HR", "People", "Human Resources", "P&C", "People & Culture"],
    "legal": ["Legal & Compliance", "Legal Services", "Office of General Counsel"],
    "operations": ["Ops", "Business Operations", "Operations & Strategy"],
    "risk": ["Risk Management", "Enterprise Risk", "Credit"],
    "compliance": ["Risk & Compliance", "Regulatory", "Financial Crime"],
    "lending": ["Business Banking", "Lending", "Commercial Banking", "Retail Banking"],
    "clinical": ["Nursing", "Clinical", "Medical", "Allied Health", "Patient Care"],
    "hse": ["HSE", "Safety", "HSEQ", "WHS"],
    "mining_ops": ["Operations", "Mining", "Site Operations", "Production"],
    "projects": ["Project Delivery", "Construction", "Delivery", "Projects & Engineering"],
    "production": ["Manufacturing", "Operations", "Plant", "Production"],
    "quality": ["QA", "Quality Assurance", "QHSE"],
    "supply_chain": ["Logistics", "Procurement", "Supply", "SCM"],
    "warehouse_ops": ["Warehouse", "Distribution", "DC Operations", "Logistics"],
    "transport": ["Fleet", "Transport & Logistics", "Linehaul", "Distribution"],
    "store_ops": ["Retail", "Stores", "Store Operations", "Retail Operations"],
    "merchandising": ["Buying", "Merchandise", "Buying & Planning"],
    "consulting": ["Advisory", "Client Services", "Consulting", "Assurance", "Tax"],
    "academic": ["Faculty", "Academic", "Teaching & Research", "School of Business"],
    "student_services": ["Student Experience", "Admissions", "Student Support"],
    EXEC_OFFICE: ["Executive", "Office of the CEO", "Leadership", "Management"],
}


def dept_label(function: str) -> str:
    return "Executive" if function == EXEC_OFFICE else FUNCTIONS[function].label


def department_owners(people: list[Person]) -> dict[str, str]:
    """function -> the function of whoever its department head reports to.

    Real cost centres often follow the reporting line: a Data team under the CFO is
    booked to Finance. This is what the department "leak" draws on."""
    by_id = {p.id: p for p in people}
    owners = {}
    for p in people:
        boss = by_id.get(p.manager_id)
        if boss and boss.function != p.function and p.function not in owners:
            owners[p.function] = boss.function
    return owners


# -- locations ---------------------------------------------------------------------------------
STATES = {"Sydney": ("NSW", "New South Wales"), "Melbourne": ("VIC", "Victoria"), "Brisbane": ("QLD", "Queensland"),
          "Perth": ("WA", "Western Australia"), "Adelaide": ("SA", "South Australia"),
          "Canberra": ("ACT", "Australian Capital Territory"), "Hobart": ("TAS", "Tasmania"),
          "Gold Coast": ("QLD", "Queensland"), "Toowoomba": ("QLD", "Queensland"), "Cooma": ("NSW", "New South Wales"),
          "Karratha": ("WA", "Western Australia"), "Port Hedland": ("WA", "Western Australia"),
          "Newman": ("WA", "Western Australia"), "Kalgoorlie": ("WA", "Western Australia"),
          "Mount Isa": ("QLD", "Queensland"), "Moranbah": ("QLD", "Queensland"), "Emerald": ("QLD", "Queensland"),
          "Olympic Dam": ("SA", "South Australia"), "Dandenong": ("VIC", "Victoria"),
          "Wetherill Park": ("NSW", "New South Wales"), "Geelong": ("VIC", "Victoria"), "Wacol": ("QLD", "Queensland"),
          "Kwinana": ("WA", "Western Australia"), "Smithfield": ("NSW", "New South Wales")}
COUNTRIES = {"Auckland": "New Zealand", "Singapore": "Singapore", "London": "United Kingdom",
             "San Francisco": "United States", "New York": "United States", "Manila": "Philippines",
             "Bangalore": "India"}
REMOTE = ["Remote", "Remote - Australia", "Work from home", "Remote (AU)"]


def render_location(city: str, rng: random.Random, mess: bool) -> str:
    if not mess:
        return city
    if city in STATES:
        abbr, state = STATES[city]
        return rng.choice([f"{city} {abbr}", f"{city}, {abbr}", f"{city}, {state}, Australia", f"Greater {city} Area",
                           f"{city}, Australia", f"{city}, AU", city.upper()])
    country = COUNTRIES.get(city, "")
    return rng.choice([f"{city}, {country}", f"Greater {city} Area", city.upper()]) if country else city


def parse_location(text: str) -> str | None:
    """Inverse of render_location, used by tests to prove the noise is recoverable."""
    if not text or text in REMOTE:
        return None
    t = text.replace("Greater ", "").replace(" Area", "")
    for city in list(STATES) + list(COUNTRIES):
        if t.lower().startswith(city.lower()):
            return city
    return None


# -- dates -----------------------------------------------------------------------------------
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def render_date(iso: str, rng: random.Random, mess: bool, year_only: bool) -> str:
    y, m = iso.split("-")
    if year_only:
        return y
    if not mess:
        return iso
    month = MONTHS[int(m) - 1]
    return rng.choice([f"{month[:3]} {y}", f"{m}/{y}", f"{month} {y}", f"{int(m)}/{y}", f"{y}/{m}"])


# -- names -----------------------------------------------------------------------------------
# First and last names drawn within one culture: "Kenji Wang" would mix Japanese and Chinese.
_ASIAN = {
    "chinese": (["Wei", "Jing", "Mei", "Xin", "Hao", "Yan", "Lei", "Ying", "Jun", "Ling"],
                ["Wang", "Li", "Zhang", "Chen", "Liu", "Huang", "Wong", "Zhou", "Wu", "Xu"]),
    "vietnamese": (["Linh", "Thanh", "Minh", "Anh", "Tuan", "Huong", "Duc", "Lan", "Quang", "Thu"],
                   ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Vu", "Dang", "Bui", "Do", "Ngo"]),
    "korean": (["Ji-woo", "Hyun", "Min-jun", "Seo-yeon", "Ji-hoon", "Soo-ah", "Dong-hyun", "Ha-eun"],
               ["Kim", "Park", "Lee", "Choi", "Jung", "Kang", "Yoon", "Han"]),
    "japanese": (["Kenji", "Yuki", "Hana", "Takumi", "Aiko", "Haruto", "Sakura", "Ren"],
                 ["Tanaka", "Sato", "Suzuki", "Takahashi", "Watanabe", "Ito", "Yamamoto", "Nakamura"]),
    "malaysian_chinese": (["Siew Ling", "Wei Ming", "Mei Fong", "Kok Wai", "Pei Shan", "Chee Keong"],
                          ["Lim", "Tan", "Ng", "Ong", "Goh", "Teo", "Chua", "Ho"]),
}
# Faker's en_AU names fall back to its US list (Hernandez, Garza...); en_GB matches
# Anglo-Australian surnames far better, so it carries most of the weight.
_LOCALES = {"en_GB": .58, "en_AU": .05, "en_NZ": .08, "en_IN": .13, "asian": .16}


class NameMaker:
    """Diverse, seeded, Australia-flavoured names. One Faker per locale, reused."""

    def __init__(self, seed: int):
        self.fakers = {loc: Faker(loc) for loc in _LOCALES if loc != "asian"}
        for i, f in enumerate(self.fakers.values()):
            f.seed_instance(seed + i)

    def make(self, rng: random.Random) -> tuple[str, str]:
        loc = rng.choices(list(_LOCALES), weights=list(_LOCALES.values()))[0]
        if loc == "asian":
            firsts, lasts = _ASIAN[rng.choice(list(_ASIAN))]
            return rng.choice(firsts), rng.choice(lasts)
        f = self.fakers[loc]
        return f.first_name(), f.last_name()


def render_name(first: str, last: str, rng: random.Random, mess: bool) -> str:
    if not mess:
        return f"{first} {last}"
    middle = rng.choice("ABCDEJKLMRST")
    return rng.choice([f"{first[0]}. {last}", f"{first} {last[0]}.", f"{last.upper()}, {first}", f"{last}, {first}",
                       f"{first} {middle}. {last}", f"{first.lower()} {last.lower()}"])


# -- one record ---------------------------------------------------------------------------------
def render_fields(p: Person, title: str, profile_name: str, owners: dict[str, str], name: tuple[str, str],
                  rng: random.Random) -> tuple[dict, list[str]]:
    """The person's flat record (everything except ids) and the field mess tags."""
    r, tags = FIELD_RATES[profile_name], []

    if rng.random() < r.title_missing:
        title = ""
        tags.append("title_missing")

    if rng.random() < r.dept_missing:
        dept = ""
        tags.append("dept_missing")
    else:
        fn = p.function
        if rng.random() < r.dept_wrong:
            fn = rng.choice([f for f in DEPT_SYNONYMS if f not in (p.function, EXEC_OFFICE)])
            tags.append("dept_wrong")
        elif p.function in owners and owners[p.function] != EXEC_OFFICE and rng.random() < r.dept_leak:
            fn = owners[p.function]
            tags.append("dept_leak")
        dept = dept_label(fn)
        if rng.random() < r.dept_synonym:
            dept = rng.choice(DEPT_SYNONYMS[fn])
            tags.append("dept_synonym")

    if rng.random() < r.loc_missing:
        location = ""
        tags.append("loc_missing")
    elif rng.random() < r.remote:
        location = rng.choice(REMOTE)
        tags.append("remote")
    else:
        mess = rng.random() < r.format_mess
        location = render_location(p.location, rng, mess)
        if mess and location != p.location:
            tags.append("loc_format")

    if rng.random() < r.date_missing:
        start = ""
        tags.append("date_missing")
    else:
        year_only = rng.random() < r.year_only
        mess = rng.random() < r.format_mess
        start = render_date(p.start_date, rng, mess, year_only)
        if year_only:
            tags.append("year_only")
        elif start != p.start_date:
            tags.append("date_format")

    mess = rng.random() < r.name_format
    full_name = render_name(*name, rng, mess)
    if mess:
        tags.append("name_format")

    return {"name": full_name, "title": title, "department": dept, "location": location,
            "start_date": start, "prev_employer": p.prev_employer or ""}, tags


if __name__ == "__main__":
    from .builder import build_company
    from .clues import add_clues, make_employer_pool
    from .mess import PROFILES, TitleContext, render_title
    from .vocabulary import load

    vocab, rng = load(), random.Random(21)
    pool, names = make_employer_pool(rng), NameMaker(21)
    for level, industry, size in [("clean", "saas", 400), ("messy", "financial_services", 700)]:
        people = build_company("demo", industry, size, rng)
        add_clues(people, industry, size, rng, pool, PROFILES[level].clues)
        owners, managers = department_owners(people), {p.manager_id for p in people}
        print(f"\n===== {level.upper()} | {industry} | {size} staff =====")
        print(f"  {'name':<22} {'title':<40} {'department':<20} {'location':<28} {'start':<10} prev employer")
        for p in rng.sample(people, 12):
            title, _ = render_title(p, TitleContext(PROFILES[level], vocab, "Acme", industry, False, p.id in managers), rng)
            rec, tags = render_fields(p, title, level, owners, names.make(rng), rng)
            print(f"  {rec['name'][:21]:<22} {rec['title'][:39]:<40} {rec['department'][:19]:<20} "
                  f"{rec['location'][:27]:<28} {rec['start_date']:<10} {rec['prev_employer'][:24]}")
