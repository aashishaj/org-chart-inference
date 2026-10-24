"""Turns the model's per-person boss probabilities into the final answer per record:
an exact edge, a partial edge ("reports up to X"), or abstain.

Exact:   the single most likely boss is likely enough.
Partial: otherwise, compute for every senior record A the probability that A is
         *somewhere above* the person, summed over all routes:
             P(A above p) = sum_b P(boss of p = b) * [b is A, or A is above b]
         Bosses are always more senior, so there are no loops and this is exact in one
         pass from the top down. Claim the most junior A whose probability clears the
         partial threshold: "reports up to Tom" when it's one of Tom's three Engineering
         Managers. Never "up to the CEO": everyone is.
Abstain: neither is likely enough, or "none of these" is the best answer (ghosts).
"""

from collections import defaultdict

from .data import Company, Prediction
from .model import Scored, score_company
from .titles import CEO

EXACT_THRESHOLD = 0.6
PARTIAL_THRESHOLD = 0.8
KEEP = 40          # ancestor entries kept per record (the rest is negligible mass)
MIN_MASS = 0.01


def ancestor_probabilities(scored: list[Scored]) -> dict[str, dict[str, float]]:
    """record -> {senior record: P(that record is somewhere above this one)}."""
    options = {s.person.rec.record_id: s.options for s in scored}
    order = sorted(scored, key=lambda s: s.person.level)  # most senior first: bosses before reports
    anc: dict[str, dict[str, float]] = {}
    for s in order:
        acc: dict[str, float] = defaultdict(float)
        for b, p in options[s.person.rec.record_id]:
            acc[b] += p
            for a, q in anc.get(b, {}).items():
                acc[a] += p * q
        top = sorted(((a, m) for a, m in acc.items() if m >= MIN_MASS), key=lambda t: -t[1])[:KEEP]
        anc[s.person.rec.record_id] = dict(top)
    return anc


def assemble(scored: list[Scored], exact_t: float = EXACT_THRESHOLD, partial_t: float = PARTIAL_THRESHOLD,
             anc: dict[str, dict[str, float]] | None = None) -> list[Prediction]:
    """`anc` can be passed in when assembling the same company at several thresholds."""
    level = {s.person.rec.record_id: s.person.level for s in scored}
    anc = anc if anc is not None else ancestor_probabilities(scored)
    out = []
    for s in scored:
        rid = s.person.rec.record_id
        if not s.options or s.p_none >= s.options[0][1] and s.p_none >= 0.5:
            out.append(Prediction(rid, None, "none", s.p_none, "no likely boss"))
            continue
        boss, prob = s.options[0]
        if prob >= exact_t:
            out.append(Prediction(rid, boss, "exact", prob, "most likely boss"))
            continue
        choices = [(a, m) for a, m in anc[rid].items() if m >= partial_t and level[a] != CEO]
        if choices:
            # Most junior qualifying person = most specific claim; ties go to more mass.
            a, m = max(choices, key=lambda t: (level[t[0]], t[1]))
            kind = "exact" if a == boss and m >= exact_t else "partial"
            out.append(Prediction(rid, a, kind, min(m, 1.0), "reports up to (shared boss of likely candidates)"))
        else:
            out.append(Prediction(rid, None, "none", s.p_none, "too uncertain"))
    return out


def orgchart(company: Company, exact_t: float = EXACT_THRESHOLD, partial_t: float = PARTIAL_THRESHOLD):
    return assemble(score_company(company), exact_t, partial_t)
