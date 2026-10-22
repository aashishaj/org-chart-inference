"""Industry templates: the recipe the tree builder follows for each company.

Two layers:
- FUNCTIONS: each department's job ladder, IC roles, team names and span of
  control. Shared across industries.
- INDUSTRIES: which departments a company in that industry has, what share of
  headcount each gets, and who each department head reports to.

All titles here are *canonical* (clean). Real-world spelling variety comes later
from the Gemini vocabulary and the mess layer.

Run `uv run python -m orgchart.generator.templates` for a review summary.
"""

from dataclasses import dataclass, field

# Seniority levels. Lower number = more senior.
CEO, EXEC, VP, HEAD, SR_MGR, MGR, SENIOR, MID, JUNIOR = range(9)
LEVEL_NAMES = {
    CEO: "CEO", EXEC: "C-suite", VP: "VP / GM", HEAD: "Head / Director",
    SR_MGR: "Senior Manager", MGR: "Manager", SENIOR: "Senior IC", MID: "IC", JUNIOR: "Junior IC",
}

# An IC role is either a base name ("Data Analyst" -> "Senior Data Analyst",
# "Data Analyst", "Junior Data Analyst") or an explicit (senior, mid, junior) triple
# for professions with their own ladder, e.g. nursing.
ICRole = str | tuple[str, str, str]


@dataclass(frozen=True)
class Function:
    label: str
    ladder: dict[int, str]          # management titles by level (EXEC..MGR); gaps allowed
    ic_roles: list[ICRole]
    teams: list[str]                # team names, used later for the team-name clue
    span: tuple[int, int] = (4, 8)  # direct reports per manager (min, max)
    exec_min_size: int | None = None  # company size from which this function gets its own C-suite exec
    reports_to: dict[str, float] = field(default_factory=lambda: {"ceo": 1.0})
    big_head_title: tuple[int, str] | None = None  # (min company size, head title) e.g. CISO at large cos
    multi_head: bool = False        # several peers at the top (e.g. Partners) instead of one head


FUNCTIONS: dict[str, Function] = {
    # ---- common functions -------------------------------------------------
    "engineering": Function(
        "Engineering",
        {EXEC: "Chief Technology Officer", VP: "VP Engineering", HEAD: "Head of Engineering",
         SR_MGR: "Senior Engineering Manager", MGR: "Engineering Manager"},
        ["Software Engineer", "Frontend Engineer", "Backend Engineer", "QA Engineer",
         "DevOps Engineer", "Mobile Engineer"],
        ["Platform", "Payments", "Mobile", "Infrastructure", "Growth", "Core API", "Integrations", "Identity"],
        span=(4, 8), exec_min_size=600,
    ),
    "product": Function(
        "Product",
        {EXEC: "Chief Product Officer", VP: "VP Product", HEAD: "Head of Product",
         SR_MGR: "Group Product Manager", MGR: "Lead Product Manager"},
        ["Product Manager", "Product Owner", "Business Analyst"],
        ["Payments", "Growth", "Platform", "Mobile", "Onboarding"],
        span=(3, 6), exec_min_size=800, reports_to={"engineering": 0.5, "ceo": 0.5},
    ),
    "design": Function(
        "Design",
        {VP: "VP Design", HEAD: "Head of Design", MGR: "Design Manager"},
        ["Product Designer", "UX Designer", "UX Researcher", "UI Designer"],
        ["Payments", "Growth", "Platform", "Mobile", "Brand"],
        span=(3, 7), reports_to={"product": 0.6, "engineering": 0.3, "marketing": 0.1},
    ),
    "data": Function(
        "Data & Analytics",
        {EXEC: "Chief Data Officer", VP: "VP Data", HEAD: "Head of Data",
         SR_MGR: "Senior Manager, Data & Analytics", MGR: "Analytics Manager"},
        ["Data Analyst", "Data Scientist", "Data Engineer", "Analytics Engineer", "BI Developer"],
        ["Analytics", "Data Platform", "Data Science", "BI", "Machine Learning"],
        span=(3, 7), exec_min_size=1500,
        reports_to={"engineering": 0.6, "finance": 0.2, "operations": 0.2},
    ),
    "security": Function(
        "Security",
        {HEAD: "Head of Information Security", SR_MGR: "Senior Security Manager", MGR: "Security Manager"},
        ["Security Engineer", "Security Analyst", "GRC Analyst", "SOC Analyst"],
        ["SecOps", "GRC", "AppSec", "Cloud Security"],
        span=(3, 6), reports_to={"engineering": 0.6, "it": 0.3, "operations": 0.1},
        big_head_title=(1000, "Chief Information Security Officer"),
    ),
    "it": Function(
        "IT",
        {EXEC: "Chief Information Officer", VP: "General Manager, Technology", HEAD: "Head of IT",
         MGR: "IT Manager"},
        ["Systems Administrator", "IT Support Analyst", "Service Desk Analyst", "Network Engineer"],
        ["Service Desk", "Infrastructure", "Enterprise Apps", "Networks"],
        span=(4, 9), exec_min_size=1000, reports_to={"finance": 0.4, "operations": 0.4, "ceo": 0.2},
    ),
    "sales": Function(
        "Sales",
        {EXEC: "Chief Revenue Officer", VP: "VP Sales", HEAD: "Head of Sales",
         SR_MGR: "Sales Director", MGR: "Sales Manager"},
        ["Account Executive", "Account Manager", "Business Development Representative",
         "Sales Development Representative"],
        ["Enterprise", "Mid-Market", "SMB", "NSW", "VIC", "QLD", "WA", "New Zealand", "APAC"],
        span=(5, 10), exec_min_size=500,
    ),
    "marketing": Function(
        "Marketing",
        {EXEC: "Chief Marketing Officer", VP: "VP Marketing", HEAD: "Head of Marketing",
         MGR: "Marketing Manager"},
        # "Manager" titles that are really ICs: a deliberate trap, common in marketing.
        ["Marketing Specialist", "Digital Marketing Specialist", "Marketing Coordinator",
         "Product Marketing Manager", "Brand Manager", "Content Marketing Manager"],
        ["Brand", "Growth", "Product Marketing", "Digital", "Events"],
        span=(3, 7), exec_min_size=600, reports_to={"ceo": 0.6, "sales": 0.4},
    ),
    "customer_success": Function(
        "Customer Success",
        {VP: "VP Customer Success", HEAD: "Head of Customer Success", MGR: "Customer Success Team Lead"},
        ["Customer Success Manager", "Onboarding Specialist", "Implementation Consultant"],  # CSM is an IC
        ["Enterprise", "Mid-Market", "SMB", "Onboarding"],
        span=(5, 9), reports_to={"sales": 0.5, "ceo": 0.3, "operations": 0.2},
    ),
    "support": Function(
        "Customer Support",
        {HEAD: "Head of Customer Support", SR_MGR: "Contact Centre Manager", MGR: "Support Team Lead"},
        ["Customer Support Specialist", "Support Engineer", "Customer Service Representative"],
        ["Tier 1", "Tier 2", "Contact Centre", "Escalations"],
        span=(8, 14), reports_to={"customer_success": 0.5, "operations": 0.5},
    ),
    "finance": Function(
        "Finance",
        {EXEC: "Chief Financial Officer", HEAD: "Financial Controller", SR_MGR: "Senior Finance Manager",
         MGR: "Finance Manager"},
        ["Accountant", "Financial Analyst", "Accounts Payable Officer", "Payroll Officer", "FP&A Analyst"],
        ["FP&A", "Accounts Payable", "Payroll", "Tax", "Treasury"],
        span=(3, 7), exec_min_size=250,
    ),
    "hr": Function(
        "People & Culture",
        {EXEC: "Chief People Officer", HEAD: "Head of People", MGR: "HR Manager"},
        ["HR Business Partner", "Talent Acquisition Partner", "Recruiter", "People & Culture Coordinator",
         "HR Advisor"],
        ["Talent Acquisition", "HR Operations", "L&D", "Reward"],
        span=(3, 7), exec_min_size=800, reports_to={"ceo": 0.6, "operations": 0.2, "finance": 0.2},
    ),
    "legal": Function(
        "Legal",
        {EXEC: "General Counsel", HEAD: "Head of Legal", MGR: "Senior Legal Counsel"},
        ["Legal Counsel", "Paralegal", "Company Secretary"],
        ["Commercial", "Corporate", "Employment", "Regulatory"],
        span=(2, 5), exec_min_size=1200, reports_to={"finance": 0.6, "ceo": 0.4},
    ),
    "operations": Function(
        "Operations",
        {EXEC: "Chief Operating Officer", VP: "VP Operations", HEAD: "Head of Operations",
         MGR: "Operations Manager"},
        ["Operations Analyst", "Operations Coordinator", "Business Operations Specialist", "Procurement Officer"],
        ["Business Operations", "Procurement", "Facilities", "Strategy"],
        span=(3, 7), exec_min_size=300,
    ),

    # ---- financial services ---------------------------------------------
    "risk": Function(
        "Risk",
        {EXEC: "Chief Risk Officer", HEAD: "Head of Risk", MGR: "Risk Manager"},
        ["Risk Analyst", "Credit Risk Analyst", "Operational Risk Specialist"],
        ["Credit Risk", "Operational Risk", "Market Risk"],
        span=(3, 7), exec_min_size=300,
    ),
    "compliance": Function(
        "Compliance",
        {HEAD: "Head of Compliance", MGR: "Compliance Manager"},
        ["Compliance Analyst", "AML Analyst", "Compliance Officer"],
        ["AML/CTF", "Regulatory Compliance", "Financial Crime"],
        span=(3, 7), reports_to={"risk": 0.6, "legal": 0.4},
    ),
    "lending": Function(
        "Lending & Banking",
        {VP: "General Manager, Business Banking", HEAD: "Head of Lending", SR_MGR: "Senior Lending Manager",
         MGR: "Lending Manager"},
        ["Relationship Manager", "Credit Analyst", "Loan Officer", "Lending Specialist"],
        ["Business Banking", "Home Loans", "Commercial", "Agribusiness", "Asset Finance"],
        span=(5, 10), reports_to={"ceo": 0.6, "operations": 0.4},
    ),

    # ---- healthcare --------------------------------------------------------
    "clinical": Function(
        "Clinical Services",
        {EXEC: "Chief Medical Officer", VP: "Executive Director of Nursing", HEAD: "Director of Nursing",
         SR_MGR: "Nurse Manager", MGR: "Nurse Unit Manager"},
        [("Clinical Nurse", "Registered Nurse", "Enrolled Nurse"),
         ("Senior Physiotherapist", "Physiotherapist", "Graduate Physiotherapist"),
         ("Senior Pharmacist", "Pharmacist", "Intern Pharmacist"),
         ("Senior Medical Officer", "Medical Officer", "Resident Medical Officer"),
         "Occupational Therapist"],
        ["Emergency", "ICU", "Surgical", "Medical Ward", "Aged Care", "Outpatients", "Rehabilitation"],
        span=(8, 15), exec_min_size=0,
    ),

    # ---- mining, construction, manufacturing, logistics -------------------
    "hse": Function(
        "Health, Safety & Environment",
        {HEAD: "Head of HSE", MGR: "HSE Manager"},
        ["HSE Advisor", "Safety Officer", "Environmental Advisor"],
        ["Safety", "Environment", "Training"],
        span=(3, 7), reports_to={"operations": 0.7, "ceo": 0.3},
    ),
    "mining_ops": Function(
        "Mining Operations",
        {VP: "General Manager Operations", HEAD: "Mine Manager", SR_MGR: "Production Superintendent",
         MGR: "Shift Supervisor"},
        ["Haul Truck Operator", "Drill Operator", "Maintenance Fitter", "Electrician", "Geologist",
         "Mining Engineer"],
        ["Open Pit", "Underground", "Processing Plant", "Maintenance", "Drill & Blast"],
        span=(8, 15), reports_to={"operations": 1.0},
    ),
    "projects": Function(
        "Projects",
        {VP: "General Manager Projects", HEAD: "Project Director", SR_MGR: "Senior Project Manager",
         MGR: "Project Manager"},
        ["Site Engineer", "Contract Administrator", "Estimator", "Site Supervisor"],
        ["Western Sydney Airport", "Metro Tunnel", "Cross River Rail", "Sydney Metro West", "Inland Rail"],
        span=(4, 9), reports_to={"operations": 0.6, "ceo": 0.4},
    ),
    "production": Function(
        "Production",
        {VP: "General Manager Manufacturing", HEAD: "Plant Manager", SR_MGR: "Production Manager",
         MGR: "Shift Supervisor"},
        ["Machine Operator", "Production Worker", "Maintenance Technician", "Process Technician",
         "Forklift Operator"],
        ["Line 1", "Line 2", "Packaging", "Assembly", "Maintenance"],
        span=(8, 16), reports_to={"operations": 1.0},
    ),
    "quality": Function(
        "Quality",
        {HEAD: "Head of Quality", MGR: "Quality Manager"},
        ["Quality Inspector", "Quality Assurance Officer", "Quality Engineer"],
        ["QA", "QC", "Continuous Improvement"],
        span=(3, 7), reports_to={"operations": 0.6, "production": 0.4},
    ),
    "supply_chain": Function(
        "Supply Chain",
        {EXEC: "Chief Supply Chain Officer", HEAD: "Head of Supply Chain", MGR: "Logistics Manager"},
        ["Supply Chain Analyst", "Demand Planner", "Warehouse Coordinator", "Procurement Specialist"],
        ["Planning", "Procurement", "Logistics", "Inventory"],
        span=(4, 8), exec_min_size=1500, reports_to={"operations": 0.8, "ceo": 0.2},
    ),
    "warehouse_ops": Function(
        "Warehouse Operations",
        {VP: "General Manager Operations", HEAD: "National Warehouse Manager", SR_MGR: "Site Manager",
         MGR: "Warehouse Supervisor"},
        ["Warehouse Operator", "Forklift Driver", "Pick Packer", "Inventory Controller"],
        ["Eastern Creek DC", "Truganina DC", "Brisbane DC", "Perth DC", "Adelaide DC"],
        span=(10, 18), reports_to={"operations": 1.0},
    ),
    "transport": Function(
        "Transport",
        {HEAD: "Head of Transport", SR_MGR: "Transport Manager", MGR: "Fleet Manager"},
        ["Truck Driver", "Linehaul Driver", "Dispatcher", "Fleet Coordinator"],
        ["Linehaul", "Metro", "Regional", "Last Mile"],
        span=(10, 18), reports_to={"operations": 1.0},
    ),

    # ---- retail ----------------------------------------------------------
    "store_ops": Function(
        "Retail Operations",
        {VP: "General Manager, Retail", HEAD: "Head of Retail Operations", SR_MGR: "Area Manager",
         MGR: "Store Manager"},
        ["Retail Assistant", "Sales Associate", "Visual Merchandiser", "Stock Controller"],
        # Store names double as the team-name clue.
        ["Bondi Junction", "Chadstone", "Westfield Sydney", "Carindale", "Garden City", "Highpoint",
         "Indooroopilly", "Doncaster", "Macquarie Centre"],
        span=(8, 18), reports_to={"operations": 0.6, "ceo": 0.4},
    ),
    "merchandising": Function(
        "Merchandise & Buying",
        {VP: "General Manager Merchandise", HEAD: "Head of Buying", MGR: "Buying Manager"},
        ["Buyer", "Assistant Buyer", "Merchandise Planner", "Allocator"],
        ["Womenswear", "Menswear", "Home", "Footwear", "Accessories"],
        span=(3, 7), reports_to={"ceo": 0.5, "operations": 0.5},
    ),

    # ---- professional services ---------------------------------------------
    "consulting": Function(
        "Client Services",
        {VP: "Partner", HEAD: "Director", SR_MGR: "Senior Manager", MGR: "Manager"},
        [("Senior Consultant", "Consultant", "Graduate Consultant"), ("Senior Analyst", "Analyst", "Associate")],
        ["Audit", "Tax", "Advisory", "Deals", "Risk Consulting", "Technology Consulting"],
        span=(3, 7), multi_head=True,  # many Partners report straight to the Managing Partner
    ),

    # ---- education -----------------------------------------------------------
    "academic": Function(
        "Academic",
        {EXEC: "Provost", VP: "Dean", HEAD: "Head of School", MGR: "Course Coordinator"},
        [("Senior Lecturer", "Lecturer", "Associate Lecturer"),
         ("Senior Research Fellow", "Research Fellow", "Research Assistant"),
         ("Senior Tutor", "Tutor", "Casual Tutor")],
        ["Business", "Engineering", "Health Sciences", "Law", "Education", "Arts"],
        span=(5, 12), exec_min_size=600,
    ),
    "student_services": Function(
        "Student Services",
        {HEAD: "Head of Student Services", MGR: "Student Services Manager"},
        ["Student Advisor", "Admissions Officer", "Enrolment Officer"],
        ["Admissions", "Student Support", "International Students"],
        span=(5, 10), reports_to={"operations": 0.5, "academic": 0.5},
    ),
}


@dataclass(frozen=True)
class Industry:
    label: str
    weight: float                     # share of companies in this industry
    functions: dict[str, float]       # function -> share of headcount (normalised in code)
    ceo_titles: dict[str, float]
    reports_to: dict[str, dict[str, float]] = field(default_factory=dict)  # overrides FUNCTIONS[...].reports_to
    exec_min_size: dict[str, int] = field(default_factory=dict)            # overrides FUNCTIONS[...].exec_min_size


_CEO_DEFAULT = {"Chief Executive Officer": 0.5, "Managing Director": 0.4, "Group CEO": 0.1}

INDUSTRIES: dict[str, Industry] = {
    "saas": Industry(
        "Software & SaaS", 0.20,
        {"engineering": .32, "product": .06, "design": .03, "data": .05, "security": .02, "it": .02,
         "sales": .14, "marketing": .07, "customer_success": .08, "support": .07, "finance": .03,
         "hr": .03, "legal": .01, "operations": .03},
        {"Chief Executive Officer": 0.6, "Co-Founder & CEO": 0.3, "Managing Director": 0.1},
        reports_to={"it": {"engineering": 0.6, "operations": 0.4}},
        exec_min_size={"engineering": 0},  # every software company has a CTO, often a founder
    ),
    "financial_services": Industry(
        "Banking & Financial Services", 0.12,
        {"engineering": .12, "data": .05, "security": .04, "it": .08, "risk": .08, "compliance": .05,
         "lending": .25, "sales": .06, "marketing": .04, "support": .08, "finance": .06, "hr": .03,
         "legal": .02, "operations": .04},
        _CEO_DEFAULT,
        reports_to={"data": {"finance": 0.4, "engineering": 0.3, "risk": 0.3},
                    "security": {"it": 0.4, "risk": 0.4, "engineering": 0.2},
                    "it": {"operations": 0.4, "finance": 0.3, "ceo": 0.3}},
    ),
    "healthcare": Industry(
        "Healthcare", 0.10,
        {"clinical": .60, "operations": .08, "finance": .05, "hr": .06, "it": .05, "data": .02,
         "security": .01, "support": .05, "quality": .04, "legal": .01, "marketing": .02},
        _CEO_DEFAULT,
        reports_to={"data": {"operations": 0.5, "finance": 0.3, "clinical": 0.2},
                    "security": {"it": 0.9, "operations": 0.1},
                    "quality": {"clinical": 0.6, "operations": 0.4}},
    ),
    "retail": Industry(
        "Retail", 0.12,
        {"store_ops": .55, "merchandising": .07, "supply_chain": .10, "marketing": .05, "engineering": .04,
         "data": .02, "it": .03, "security": .01, "finance": .04, "hr": .04, "legal": .01,
         "operations": .02, "support": .02},
        _CEO_DEFAULT,
        reports_to={"data": {"marketing": 0.4, "finance": 0.3, "operations": 0.3},
                    "security": {"it": 1.0},
                    "engineering": {"it": 0.6, "ceo": 0.4}},
        exec_min_size={"engineering": 1200},  # retailers rarely have a CTO until they're big
    ),
    "mining": Industry(
        "Mining & Resources", 0.08,
        {"mining_ops": .55, "hse": .06, "supply_chain": .07, "operations": .05, "finance": .05, "hr": .05,
         "it": .04, "security": .01, "data": .02, "legal": .02},
        _CEO_DEFAULT,
        reports_to={"data": {"operations": 0.6, "finance": 0.4}, "security": {"it": 1.0},
                    "it": {"finance": 0.6, "operations": 0.4}},
        exec_min_size={"operations": 0},  # mining companies always have a COO
    ),
    "professional_services": Industry(
        "Professional Services", 0.12,
        {"consulting": .70, "marketing": .04, "finance": .05, "hr": .05, "it": .04, "security": .01,
         "data": .02, "legal": .04, "operations": .03, "sales": .02},
        {"Managing Partner": 0.7, "Chief Executive Officer": 0.3},
        reports_to={"data": {"operations": 0.5, "finance": 0.5}, "security": {"it": 1.0},
                    "it": {"operations": 0.5, "finance": 0.5}},
    ),
    "manufacturing": Industry(
        "Manufacturing", 0.08,
        {"production": .50, "quality": .07, "supply_chain": .12, "it": .04, "data": .02, "security": .01,
         "sales": .07, "marketing": .03, "finance": .05, "hr": .04, "hse": .04, "operations": .03,
         "legal": .01},
        _CEO_DEFAULT,
        reports_to={"data": {"operations": 0.5, "finance": 0.5}, "security": {"it": 1.0},
                    "it": {"finance": 0.5, "operations": 0.5}},
        exec_min_size={"operations": 0},
    ),
    "education": Industry(
        "Education", 0.06,
        {"academic": .55, "student_services": .10, "it": .06, "security": .01, "data": .02,
         "marketing": .05, "finance": .06, "hr": .06, "legal": .01, "operations": .06},
        {"Chief Executive Officer": 0.5, "Vice-Chancellor": 0.3, "Principal": 0.2},
        reports_to={"data": {"operations": 0.5, "finance": 0.3, "academic": 0.2}, "security": {"it": 1.0},
                    "it": {"operations": 0.6, "finance": 0.4}},
    ),
    "construction": Industry(
        "Construction & Property", 0.08,
        {"projects": .55, "hse": .07, "supply_chain": .06, "finance": .06, "hr": .04, "it": .04,
         "security": .01, "data": .01, "legal": .03, "operations": .05, "sales": .04, "marketing": .02},
        _CEO_DEFAULT,
        reports_to={"data": {"finance": 0.5, "operations": 0.5}, "security": {"it": 1.0},
                    "it": {"finance": 0.5, "operations": 0.5}},
    ),
    "logistics": Industry(
        "Transport & Logistics", 0.04,
        {"warehouse_ops": .40, "transport": .25, "supply_chain": .05, "engineering": .03, "data": .02,
         "it": .04, "security": .01, "sales": .06, "support": .05, "finance": .04, "hr": .03,
         "operations": .02},
        _CEO_DEFAULT,
        reports_to={"data": {"operations": 0.6, "engineering": 0.2, "finance": 0.2}, "security": {"it": 1.0}},
        exec_min_size={"operations": 0},
    ),
}


def head_reports_to(industry: str, function: str) -> dict[str, float]:
    """Where this function's head reports, as {target function or 'ceo': probability}.

    Targets the industry doesn't have are dropped and the rest renormalised, so the
    shared defaults degrade gracefully (support -> customer_success at a bank falls
    back to operations). If nothing is left, the head reports to the CEO.
    """
    ind = INDUSTRIES[industry]
    dist = ind.reports_to.get(function, FUNCTIONS[function].reports_to)
    kept = {t: p for t, p in dist.items() if t == "ceo" or t in ind.functions}
    total = sum(kept.values())
    return {t: p / total for t, p in kept.items()} if total else {"ceo": 1.0}


def exec_min_size(industry: str, function: str) -> int | None:
    return INDUSTRIES[industry].exec_min_size.get(function, FUNCTIONS[function].exec_min_size)


def validate() -> list[str]:
    """Return a list of problems with the templates; empty means they're consistent."""
    problems = []
    for key, ind in INDUSTRIES.items():
        for fn in ind.functions:
            if fn not in FUNCTIONS:
                problems.append(f"{key}: unknown function {fn!r}")
        # Industry-specific overrides are deliberate, so their targets must exist.
        # (Shared defaults fall back gracefully; see head_reports_to.)
        for fn, dist in ind.reports_to.items():
            for target in dist:
                if target != "ceo" and target not in ind.functions:
                    problems.append(f"{key}: {fn} reports to {target!r}, which this industry doesn't have")
        # No reporting cycles between functions (A's head under B's head under A's head).
        for fn in ind.functions:
            seen, frontier = {fn}, set(head_reports_to(key, fn)) - {"ceo"}
            while frontier:
                t = frontier.pop()
                if t == fn:
                    problems.append(f"{key}: reporting cycle through {fn}")
                    break
                if t in seen or t not in ind.functions:
                    continue
                seen.add(t)
                frontier |= set(head_reports_to(key, t)) - {"ceo"}
    for key, f in FUNCTIONS.items():
        if f.span[0] < 1 or f.span[0] > f.span[1]:
            problems.append(f"{key}: bad span {f.span}")
    for key, ind in INDUSTRIES.items():
        for name, dist in [("ceo_titles", ind.ceo_titles), *((f"reports_to[{k}]", v) for k, v in ind.reports_to.items())]:
            if abs(sum(dist.values()) - 1) > 1e-6:
                problems.append(f"{key}: {name} probabilities sum to {sum(dist.values()):.2f}")
    if abs(sum(i.weight for i in INDUSTRIES.values()) - 1) > 1e-6:
        problems.append("industry weights don't sum to 1")
    return problems


def _fmt_targets(dist: dict[str, float]) -> str:
    return ", ".join(f"{'CEO' if t == 'ceo' else FUNCTIONS[t].label} {p:.0%}" for t, p in dist.items())


if __name__ == "__main__":
    problems = validate()
    print("Validation:", "OK" if not problems else "\n  " + "\n  ".join(problems))
    for key, ind in INDUSTRIES.items():
        total = sum(ind.functions.values())
        print(f"\n== {ind.label} ({ind.weight:.0%} of companies) | CEO: {', '.join(ind.ceo_titles)}")
        for fn, share in sorted(ind.functions.items(), key=lambda kv: -kv[1]):
            emin = exec_min_size(key, fn)
            exec_note = "" if emin is None else f" | own exec from {emin}+ staff"
            print(f"  {FUNCTIONS[fn].label:<30} {share / total:>4.0%}  head -> {_fmt_targets(head_reports_to(key, fn))}{exec_note}")
