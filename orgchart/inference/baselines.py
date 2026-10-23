"""Deliberately naive engines that set the floor every real engine must beat.

- ceo_only: "everyone reports up to the CEO". Always true for real employees,
  useless in practice. Exists to prove the scorecard can't be gamed by vague claims.
- keyword: crude seniority keywords + department, attach each person to the
  nearest more-senior record in the same department. The obvious first idea, and
  a demonstration of why titles alone produce wrong edges.
"""

import re

from .data import Company, Prediction, Record

_TOP = re.compile(r"\b(ceo|chief executive|managing director|managing partner|vice[- ]chancellor|founder|md)\b", re.I)
# Checked in order; first match wins. Lower = more senior.
_LEVELS = [
    (1, r"\b(chief|cfo|cto|coo|cio|cmo|cro|cpo|ciso|cdo|general counsel|provost)\b"),
    (2, r"\b(vp|vice president|general manager|gm|partner|dean)\b"),
    (3, r"\b(head|director)\b"),
    (4, r"\b(senior manager|area manager|superintendent)\b"),
    (5, r"\b(manager|mgr|lead|supervisor|team leader|coordinator)\b"),
    (6, r"\b(senior|sr|snr|principal|staff)\b"),
    (8, r"\b(junior|jr|jnr|graduate|grad|intern|trainee|assistant)\b"),
]
_LEVELS = [(lvl, re.compile(p, re.I)) for lvl, p in _LEVELS]
_DEPT_WORDS = ["engineer", "developer", "devops", "sales", "account", "marketing", "finance", "accountant", "payroll",
               "hr", "people", "talent", "recruit", "data", "analytics", "security", "nurse", "clinical", "store",
               "retail", "warehouse", "driver", "transport", "project", "site", "quality", "legal", "counsel", "risk",
               "compliance", "lending", "credit", "customer", "support", "product", "design", "operations", "it",
               "lecturer", "student", "buying", "supply", "production", "mining", "safety", "consult"]


_ASSISTANT = re.compile(r"\b(assistant|ea|pa)\b|\bto (the )?(ceo|md|chief)", re.I)


def _level(title: str) -> int:
    # "Executive Assistant to the CEO" contains "CEO": without this the EA becomes the top
    # of the company in about half of all companies.
    if _TOP.search(title) and not _ASSISTANT.search(title):
        return 0
    return next((lvl for lvl, rx in _LEVELS if rx.search(title)), 7)


def _dept(r: Record) -> str:
    if r.department:
        return r.department.lower()
    t = r.title.lower()
    return next((w for w in _DEPT_WORDS if re.search(rf"\b{w}", t)), "")


def _top(records: list[Record]) -> Record:
    tops = [r for r in records if _level(r.title) == 0]
    return min(tops or records, key=lambda r: (_level(r.title), r.start_date or "9999"))


def ceo_only(company: Company) -> list[Prediction]:
    top = _top(company.records)
    return [Prediction(r.record_id, None, "none", 1.0) if r is top else
            Prediction(r.record_id, top.record_id, "partial", 0.99, "everyone reports up to the top")
            for r in company.records]


def keyword(company: Company) -> list[Prediction]:
    top = _top(company.records)
    info = [(r, _level(r.title), _dept(r)) for r in company.records]
    out = []
    for r, lvl, dept in info:
        if r is top:
            out.append(Prediction(r.record_id, None, "none", 0.5))
            continue
        above = [(c, cl) for c, cl, cd in info if c is not r and cl < lvl and dept and cd == dept]
        if not above:
            out.append(Prediction(r.record_id, top.record_id, "partial", 0.5, "no department match"))
            continue
        nearest = max(cl for _, cl in above)
        best = min((c for c, cl in above if cl == nearest),
                   key=lambda c: (c.location != r.location, c.start_date or "9999"))
        out.append(Prediction(r.record_id, best.record_id, "exact", 0.5, "nearest more-senior in department"))
    return out
