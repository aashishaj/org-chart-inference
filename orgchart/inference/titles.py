"""Rule-based title parser: raw title -> level, department, team qualifier, flags.

Written from general knowledge of how job titles work (and must not use anything
from the generator; see tests/test_no_peeking.py). Pipeline:

1. clean: strip emojis and LinkedIn fluff, "@ Company", keep team-like "| Payments"
2. flags: contractor, acting/interim, executive assistant ("... to the CEO")
3. undo inversions: "Director, Managing" -> "managing director"
4. expand abbreviations, fix typos against known title words
5. seniority rules, most specific first
6. department from title phrases, then the department field, then the industry

Each answer carries a confidence so low-confidence titles can go to Gemini.

Levels: 0 CEO, 1 C-suite, 2 VP/GM/Partner, 3 Head/Director, 4 Senior Manager,
5 Manager/Lead, 6 Senior IC, 7 IC, 8 Junior IC.
"""

import difflib
import re
from dataclasses import dataclass, field
from functools import lru_cache

CEO, EXEC, VP, HEAD, SR_MGR, MGR, SENIOR, MID, JUNIOR = range(9)


@dataclass(frozen=True)
class ParsedTitle:
    level: int | None
    level_conf: float
    function: str | None
    function_conf: float
    qualifiers: tuple[str, ...] = ()
    flags: frozenset[str] = field(default_factory=frozenset)
    core: str = ""
    rule: str = ""

    @property
    def confidence(self) -> float:
        return min(self.level_conf, self.function_conf)


# -- 1-3: cleaning -------------------------------------------------------------------------------
_FLUFF = re.compile(r"hiring|building|helping|passionate|speaker|mentor|open to|opportunit|ex-|grow|"
                    r"people leader|innovat|transform|award", re.I)
_AT_COMPANY = re.compile(r"\s(@|at)\s+[A-Z].*$")
_SYMBOLS = re.compile(r"[^\w\s&/,()\-–|.'+]")
_CONTRACT = re.compile(r"\(\s*(contract|contractor|fixed term)\s*\)|\bcontractor\b|\bfixed[- ]term\b|"
                       r"^contract\s+(?!administrator|manager|specialist|analyst|lawyer|officer)|\s-\s*contract$|\(via [^)]*\)|\bvia\s+.*$", re.I)
_CONSULTANT_VIA = re.compile(r"^consultant\s*-\s*(.+?)\s*\([^)]*\)$", re.I)
_ACTING = re.compile(r"^(acting|interim)\s+|^a/\s*|\(\s*(acting|interim)\s*\)", re.I)
_SENIORITY_WORDS = {"senior", "junior", "graduate", "managing", "chief", "executive", "general", "lead",
                    "principal", "associate", "assistant", "deputy", "group"}
_REDUNDANT_ACRONYM = re.compile(r"^[a-z&]{2,5}$")  # "(CSM)", "(RGN)", "(BDR)" repeat the title
# A segment that starts with a seniority word is the front half of an inverted title.
_INVERTED_ROLE = re.compile(r"^(senior|snr|sr\.?|chief|chf|general|group|junior|graduate)\s+\w")


def _split_segments(s: str) -> list[str]:
    return [p.strip() for p in re.split(r"\s+[-–]\s+|,\s*|\s+–\s*", s) if p.strip()]


# -- 4: abbreviations and typos -----------------------------------------------------------------
_ABBREV = {
    "mgr": "manager", "mngr": "manager", "mgmt": "management", "snr": "senior", "sr": "senior", "jr": "junior",
    "jnr": "junior", "grad": "graduate", "dir": "director", "gm": "general manager", "md": "managing director",
    "ops": "operations", "mktg": "marketing", "acct": "account", "acc": "account", "exec": "executive",
    "assoc": "associate", "asst": "assistant", "eng": "engineering", "engr": "engineer", "dev": "developer",
    "admin": "administrator", "coord": "coordinator", "spec": "specialist", "rep": "representative",
    "bus": "business", "biz": "business", "s/w": "software", "sw": "software", "tech": "technology",
    "rn": "registered nurse", "csr": "customer service representative", "csm": "customer success manager",
    "bdr": "business development representative", "sdr": "sales development representative",
    "ae": "account executive", "ba": "business analyst", "ta": "talent acquisition", "hrbp": "hr business partner",
    "bp": "business partner", "chf": "chief", "infosec": "information security", "mo": "medical officer",
    "don": "director of nursing", "rm": "relationship manager", "am": "account manager", "en": "enrolled nurse", "anlst": "analyst", "num": "nurse unit manager", "vc": "vice chancellor", "hse": "hse",
    "iii": "senior", "ii": "", "svp": "svp", "evp": "evp", "fin": "finance", "info": "information",
    "sys": "systems", "ux/ui": "ux ui", "ui/ux": "ux ui", "qc": "quality control", "whs": "safety",
}


# -- 5: seniority -------------------------------------------------------------------------------------
def _rx(p: str) -> re.Pattern:
    return re.compile(p)


# Manager-titled roles that usually manage no one.
_IC_MANAGER = _rx(r"\b(product|account|key account|customer success|relationship|brand|product marketing|"
                  r"content( marketing)?|community|campaign|case|social media|category|portfolio|partnerships?) manager\b")
_PEOPLE_MANAGER_SENIOR = _rx(r"\bsenior\b.*\bmanager\b")
_LEVEL_RULES: list[tuple[re.Pattern, int, float, str]] = [
    (_rx(r"\b(executive|personal) assistant\b|\bassistant to\b|\bea to\b"), MID, .9, "assistant"),
    (_rx(r"\bchief of staff\b"), HEAD, .9, "chief of staff"),
    (_rx(r"\b(chief executive( officer)?|ceo|managing director|managing partner|vice chancellor|group ceo)\b"),
     CEO, .95, "ceo"),
    (_rx(r"^(co-? ?founder|founder|president|principal|school principal|college principal)$"), CEO, .6,
     "founder/principal"),
    (_rx(r"\bchief information security officer\b|\bciso\b"), HEAD, .75, "ciso"),
    (_rx(r"\bchief\b.*\bofficer\b|\b(cfo|cto|coo|cio|cmo|cro|cpo|chro|cdo|cco|cso)\b|\bgeneral (legal )?counsel\b|"
         r"\bprovost\b|\bchief (financial|technology|operating|marketing|revenue|people|risk|medical|data)\b"),
     EXEC, .9, "c-suite"),
    (_rx(r"\bassociate director\b"), SR_MGR, .75, "associate director"),
    (_rx(r"\b(vice president|vp|svp|evp)\b"), VP, .9, "vp"),
    (_rx(r"\bavp\b"), HEAD, .7, "avp"),
    (_rx(r"\bgeneral manager\b"), VP, .85, "general manager"),
    (_rx(r"\bexecutive director\b"), VP, .6, "executive director"),
    (_rx(r"(?<!business )(?<!acquisition )(?<!hr )(?<!talent )(?<!people )(?<!resources )(?<!culture )(?<!finance )(?<!learning )\bpartner\b"), VP, .75, "partner"),
    (_rx(r"\bdean\b"), VP, .8, "dean"),
    (_rx(r"\bhead\b"), HEAD, .9, "head"),
    (_rx(r"\b(mine|plant|national \w+) manager\b|\bfinancial controller\b|\bproject director\b"), HEAD, .7,
     "site/plant head"),
    (_rx(r"\bdirector\b"), HEAD, .8, "director"),
    (_rx(r"\bsenior manager\b"), SR_MGR, .85, "senior manager"),
    (_IC_MANAGER, None, .75, "ic-manager"),  # level decided by seniority words below
    (_PEOPLE_MANAGER_SENIOR, SR_MGR, .7, "senior x manager"),
    (_rx(r"\b(area (\w+ )?manager|superintendent|group product manager|contact centre manager|site manager|"
         r"production manager|transport manager|nurse manager)\b"), SR_MGR, .7, "senior-manager role"),
    (_rx(r"\b(manager|management|team lead|team leader|lead|supervisor|foreman|course coordinator)\b"), MGR, .8,
     "manager"),
    (_rx(r"\b(junior|graduate|intern|internship|trainee|apprentice|cadet|enrolled nurse|resident medical officer|"
         r"research assistant|casual tutor|associate lecturer|assistant buyer)\b"), JUNIOR, .85, "junior"),
    (_rx(r"\b(senior|principal|staff|clinical nurse|registrar|senior lecturer)\b"), SENIOR, .85, "senior"),
    (_rx(r"^(assistant|associate) \w+"), JUNIOR, .55, "assistant/associate x"),  # Assistant Buyer, Associate Lecturer
]
_VAGUE = {"manager": MGR, "team leader": MGR, "director": HEAD, "leader": MGR, "management": MGR,
          "consultant": MID, "team member": MID, "staff": MID, "specialist": MID, "associate": MID,
          "analyst": MID, "employee": MID, "lead": MGR}


# -- 6: departments -----------------------------------------------------------------------------------------
# Most specific phrases first: "data engineer" is Data, not Engineering.
_FUNCTION_PHRASES: list[tuple[str, str]] = [
    ("executive", r"\b(ceo|chief executive|managing director|managing partner|vice chancellor|chief of staff|"
                  r"executive assistant|personal assistant|founder|president)\b"),
    ("security", r"\b(security|infosec|cyber|ciso|soc analyst|grc|appsec)\b"),
    ("data", r"\b(data|analytics|bi developer|business intelligence|machine learning|insights|cdo)\b"),
    ("design", r"\b(designer|ux|ui|design|user research)\b"),
    ("product", r"\b(product manager|product owner|product lead|head of product|cpo|business analyst|"
                r"vp product|product management|product)\b(?! marketing)"),
    ("it", r"\b(it|information technology|systems administrator|sysadmin|service desk|helpdesk|help desk|"
           r"network engineer|network|cio|desktop support|it support)\b"),
    ("compliance", r"\b(compliance|aml|financial crime|ctf)\b"),
    ("risk", r"\b(risk|cro|credit risk)\b"),
    ("lending", r"\b(lending|loan|relationship manager|credit analyst|business banking|mortgage|banker)\b"),
    ("clinical", r"\b(nurse|nursing|medical officer|doctor|registrar|physiotherap|physio|pharmac|occupational "
                 r"therap|clinical|midwife|clinician|ward|cmo|medical)\w*"),
    ("hse", r"\b(hse|safety|environment|environmental|whs|hseq)\b"),
    ("mining_ops", r"\b(haul|drill|fitter|geologist|mining|mine|blast|superintendent|processing plant|dump truck|"
                   r"electrician|truck operator)\w*"),
    ("warehouse_ops", r"\b(warehouse|pick packer|picker|packer|inventory controller|distribution centre|dc)\b"),
    ("transport", r"\b(driver|linehaul|dispatcher|fleet|transport)\b"),
    ("projects", r"\b(project director|project manager|site engineer|contract administrator|estimator|"
                 r"site supervisor|construction|project engineer|projects)\b"),
    ("production", r"\b(machine operator|production|process technician|plant manager|assembly|packaging|"
                   r"manufacturing|maintenance technician|shift supervisor|forklift operator)\b"),
    ("quality", r"\b(quality|qa officer|quality assurance|quality control|qc|inspector)\b"),
    ("supply_chain", r"\b(supply chain|logistics|demand planner|procurement|planner|inventory)\b"),
    ("store_ops", r"\b(store|shop|retail|sales associate|visual merchandiser|stock controller|area manager)\b"),
    ("merchandising", r"\b(buyer|buying|merchandise|allocator)\b"),
    ("academic", r"\b(lecturer|tutor|professor|research fellow|research assistant|dean|head of school|"
                 r"course coordinator|provost|faculty|academic)\b"),
    ("student_services", r"\b(student|admissions|enrolment|enrollment)\b"),
    ("support", r"\b(support engineer|support specialist|technical support)\b"),
    ("engineering", r"\b(software|engineer|engineering|developer|devops|frontend|front end|backend|back end|"
                    r"mobile|qa engineer|sre|cto|architect|programmer|full stack|ios|android|test engineer)\b"),
    ("customer_success", r"\b(customer success|onboarding|implementation|client success|customer experience)\b"),
    ("support", r"\b(support|customer service|contact centre|call centre|customer care)\b"),
    ("sales", r"\b(sales|account executive|account manager|business development|cro|revenue|"
              r"sales development)\b"),
    ("marketing", r"\b(marketing|brand|content|digital|cmo|communications|comms|seo|growth)\b"),
    ("finance", r"\b(finance|financial|accountant|accounting|accounts payable|payroll|fp&a|cfo|controller|"
                r"treasury|tax|bookkeeper)\b"),
    ("hr", r"\b(hr|human resources|people|talent|recruit\w*|chro|culture|l&d|learning)\b"),
    ("legal", r"\b(legal|counsel|paralegal|lawyer|solicitor|company secretary)\b"),
    ("operations", r"\b(operations|coo|facilities|strategy|business operations|operational)\b"),
    ("consulting", r"\b(consultant|consulting|advisory|audit|partner|client services)\b"),
]
_FUNCTION_RX = [(f, re.compile(p)) for f, p in _FUNCTION_PHRASES]

# Generic words that mean different departments in different industries.
_INDUSTRY_DEFAULTS = {
    "professional": "consulting", "education": "academic", "health": "clinical", "retail": "store_ops",
    "mining": "mining_ops", "construction": "projects", "manufacturing": "production", "logistics": "warehouse_ops",
    "transport": "warehouse_ops", "banking": "lending", "financial": "lending", "software": "engineering",
}
_INDUSTRY_GENERIC = re.compile(r"^(consultant|analyst|associate|partner|director|manager|senior consultant|"
                               r"team member|staff|specialist|operator|supervisor|officer)$")

# Words the typo fixer may correct *towards*. Built from whole words only (regex
# fragments like "physiotherap" would turn correct words into stems).
_COMMON_TITLE_WORDS = """manager director officer engineer developer analyst specialist consultant executive
representative coordinator administrator designer nurse accountant counsel partner president supervisor
lecturer tutor scientist operator driver buyer assistant associate advisor adviser owner architect recruiter
controller technician inspector fitter electrician geologist therapist pharmacist physiotherapist planner clerk
merchandiser fellow professional researcher strategist marketing engineering operations finance financial
security software senior junior graduate principal business development customer success support service
product people talent clinical registered enrolled medical warehouse transport retail project projects
quality safety environmental procurement logistics supply chain lending relationship compliance analytics
payroll treasury infrastructure network systems platform frontend backend mobile digital content brand
partnerships acquisition learning culture resources student admissions enrolment research teaching
occupational pharmacy physiotherapy contract administrator estimator superintendent foreman production
maintenance assembly packaging machine process inventory dispatcher linehaul fleet""".split()
_KNOWN_TOKENS = sorted({t for _, p in _FUNCTION_PHRASES for t in re.findall(r"\b[a-z]{5,}\b", p)}
                       | {w for w in _COMMON_TITLE_WORDS if len(w) >= 5})


@lru_cache(maxsize=50_000)
def _fix_token(tok: str) -> str:
    if len(tok) < 5 or tok in _KNOWN_TOKENS_SET or not tok.isalpha():
        return tok
    # Real typos almost never change the first letter; requiring it stops correct
    # words being "fixed" into others ("resident" -> "president").
    candidates = [t for t in _KNOWN_TOKENS if t[0] == tok[0]]
    match = difflib.get_close_matches(tok, candidates, n=1, cutoff=0.85)
    return match[0] if match else tok


_KNOWN_TOKENS_SET = set(_KNOWN_TOKENS)


def _expand(s: str) -> str:
    s = s.replace("co-ordinator", "coordinator").replace("co - ordinator", "coordinator")
    s = re.sub(r"\beng$", "engineer", s)
    s = re.sub(r"\bdev$", "developer", s)
    tokens = []
    for tok in re.findall(r"[a-z0-9&/']+|[^\sa-z0-9&/']", s):
        tok = _ABBREV.get(tok, tok)
        tokens.append(" ".join(_fix_token(t) for t in tok.split()) if tok else "")
    return re.sub(r"\s+", " ", " ".join(t for t in tokens if t)).strip()


def _industry_key(industry: str) -> str | None:
    i = industry.lower()
    return next((v for k, v in _INDUSTRY_DEFAULTS.items() if k in i), None)


# -- the parser ----------------------------------------------------------------------------------------------
@lru_cache(maxsize=200_000)
def parse_title(raw: str, industry: str = "") -> ParsedTitle:
    flags: set[str] = set()
    s = (raw or "").strip()
    if not s:
        return ParsedTitle(None, 0.0, None, 0.0, flags=frozenset({"blank"}))

    # 1. fluff and "@ Company"
    s = _AT_COMPANY.sub("", s)
    parts = [p.strip() for p in s.split("|")]
    s, qualifiers = parts[0], []
    for extra in parts[1:]:
        if not extra or _FLUFF.search(extra) or not re.search(r"[A-Za-z]", extra):
            flags.add("fluff")
        else:
            qualifiers.append(extra)
    s = _SYMBOLS.sub(" ", s).strip()
    if s.isupper() and len(s) > 4:
        flags.add("allcaps")
    s = s.lower()

    # 2. flags
    if m := _CONSULTANT_VIA.match(s):
        s, flags = m.group(1), flags | {"contractor"}
    if _CONTRACT.search(s):
        s = _CONTRACT.sub(" ", s).strip(" -")
        flags.add("contractor")
    if _ACTING.search(s):
        s = _ACTING.sub(" ", s).strip()
        flags.add("acting")
    s = re.sub(r"\s*-\s*graduate program$", " graduate", s)

    # Parentheses: seniority moves to the front, acronyms are redundant, the rest is a qualifier.
    prefix = []
    for inner in re.findall(r"\(([^)]*)\)", s):
        w = inner.strip().lower()
        if w in _SENIORITY_WORDS:
            prefix.append(w)
        elif not _REDUNDANT_ACRONYM.match(w):
            qualifiers.append(inner.strip())
    s = re.sub(r"\([^)]*\)", " ", s).strip()

    # 3. segments: find the role, undo inversions
    segments = _split_segments(s) or [s]
    core_i = next((i for i, seg in enumerate(segments) if _role_like(seg)), 0)
    core = segments[core_i]
    for i, seg in enumerate(segments):
        if i == core_i:
            continue
        w = seg.strip().lower()
        if w in _SENIORITY_WORDS or w in ("senior", "junior", "graduate"):
            prefix.append(w)                       # "Director, Managing" -> "managing director"
        elif _INVERTED_ROLE.match(w) and len(core.split()) == 1:
            core = f"{w} {core}"                   # "Manager, Senior Engineering", "Officer, Chief Medical"
        elif core.strip() in ("head",):
            core = f"head of {seg}"                # "Head, Information Security"
        elif core.endswith(" officer") and w in ("chief",):
            prefix.append(w)
        else:
            qualifiers.append(seg)
    core = _expand(" ".join(prefix + [core]))
    quals = tuple(_expand(q.lower()) for q in qualifiers if q.strip())

    level, level_conf, rule = _level(core)
    function, function_conf = _function(core, quals, industry)

    if core in _VAGUE or (level is None and function is None):
        flags.add("vague")
        if core in _VAGUE:
            level, level_conf, rule = _VAGUE[core], 0.4, "vague"
        if function is None and _INDUSTRY_GENERIC.match(core) and (ind := _industry_key(industry)):
            function, function_conf = ind, 0.4
    if "assistant" == rule:
        function, function_conf = "executive", 0.85
    return ParsedTitle(level, level_conf, function, function_conf, quals, frozenset(flags), core, rule)


_ROLE_WORDS = re.compile(r"\b(manager|director|head|officer|engineer|developer|analyst|specialist|consultant|"
                         r"lead|leader|executive|representative|coordinator|administrator|designer|nurse|"
                         r"accountant|counsel|partner|president|ceo|cfo|cto|coo|vp|gm|md|supervisor|lecturer|"
                         r"tutor|scientist|operator|driver|buyer|assistant|associate|advisor|adviser|owner|"
                         r"architect|recruiter|controller|technician|inspector|fitter|electrician|geologist|"
                         r"therapist|pharmacist|physiotherapist|planner|clerk|dean|provost|chief|mgr|eng|dev|"
                         r"rep|admin|intern|graduate|apprentice|staff|member|employee|superintendent|foreman|"
                         r"estimator|allocator|paralegal|secretary|picker|packer|dispatcher|registrar|doctor|"
                         r"merchandiser|fellow|professional|worker|researcher|strategist)\b")


def _role_like(seg: str) -> bool:
    return bool(_ROLE_WORDS.search(seg.lower()))


def _level(core: str) -> tuple[int | None, float, str]:
    for rx, level, conf, rule in _LEVEL_RULES:
        if not rx.search(core):
            continue
        if rule == "ic-manager":  # manager-titled IC: seniority comes from other words
            if re.search(r"\bgroup product manager\b", core):
                return SR_MGR, conf, rule      # manages product managers
            if re.search(r"\b(senior|principal|lead|group)\b", core):
                return SENIOR, conf, rule
            if re.search(r"\b(junior|graduate|associate|assistant)\b", core):
                return JUNIOR, conf, rule
            return MID, conf, rule
        return level, conf, rule
    if re.search(r"\bi$", core):
        return JUNIOR, .7, "roman i"
    if _role_like(core):
        return MID, .7, "default ic"
    return None, 0.0, ""


_SITE_FUNCTIONS = {"mining_ops", "production", "warehouse_ops", "transport"}
# Words that mean "site worker" in any heavy industry; the industry says which site.
_SITE_AMBIGUOUS = re.compile(r"\b(shift supervisor|supervisor|electrician|fitter|operator|maintenance|forklift)\b")


def _function(core: str, quals: tuple[str, ...], industry: str) -> tuple[str | None, float]:
    ind = _industry_key(industry)
    whole = " ".join((core,) + quals)
    # Inverted titles put the specialty after the comma: "Engineer, Security" is a
    # security engineer, "Operator, Machine" a machine operator. Try those first.
    texts = [(f"{q} {core}", .85) for q in quals] + [(core, .9)] + [(q, .7) for q in quals]
    for text, conf in texts:
        for f, rx in _FUNCTION_RX:
            if rx.search(text):
                # Industry decides between look-alikes: "sales associate" in retail is store staff,
                # a "shift supervisor" or "electrician" at a miner is mining, at a factory production.
                if f == "sales" and ind == "store_ops" and re.search(r"\b(associate|assistant)\b", whole):
                    return "store_ops", conf
                if f in _SITE_FUNCTIONS and ind in _SITE_FUNCTIONS and _SITE_AMBIGUOUS.search(text):
                    return ind, conf
                if f == "consulting" and ind != "consulting":
                    continue  # "consultant" outside professional services isn't the consulting practice
                return f, conf
    return None, 0.0


def department_function(department: str) -> str | None:
    """Department field -> function, using the same phrases plus common department shorthand."""
    d = department.lower().strip()
    if not d:
        return None
    shorthand = {"eng": "engineering", "r&d": "engineering", "tech": "engineering", "technology": "engineering",
                 "p&c": "hr", "people": "hr", "cx": "customer_success", "cs": "customer_success", "ops": "operations",
                 "fin": "finance", "scm": "supply_chain", "faculty": "academic", "stores": "store_ops",
                 "plant": "production", "delivery": "projects", "advisory": "consulting", "assurance": "consulting",
                 "client services": "consulting", "executive": "executive", "leadership": "executive",
                 "office of the ceo": "executive", "management": "executive", "credit": "risk",
                 "ict": "it", "insights": "data", "bi": "data", "revenue": "sales", "commercial": "sales"}
    if d in shorthand:
        return shorthand[d]
    f, _ = _function(_expand(d), (), "")
    return f
