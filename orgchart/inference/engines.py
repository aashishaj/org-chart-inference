"""Registry of inference engines. Each takes one Company and returns one Prediction
per record."""

from collections.abc import Callable
from functools import partial

from .assemble import orgchart
from .baselines import ceo_only, keyword
from .data import Company, Prediction
from .model import score_company

GREEDY_THRESHOLD = 0.5
# Strictness presets for the full engine: (exact threshold, partial threshold).
PRESETS = {"strict": (0.9, 0.8), "balanced": (0.8, 0.7), "broad": (0.5, 0.6)}


def greedy(company: Company, threshold: float = GREEDY_THRESHOLD) -> list[Prediction]:
    """Each person's most likely boss, independently; abstain below the threshold."""
    out = []
    for s in score_company(company):
        rid = s.person.rec.record_id
        if s.options and s.options[0][1] >= threshold and s.options[0][1] > s.p_none:
            boss, prob = s.options[0]
            out.append(Prediction(rid, boss, "exact", prob, "learned, greedy"))
        else:
            out.append(Prediction(rid, None, "none", s.p_none))
    return out


ENGINES: dict[str, Callable[[Company], list[Prediction]]] = {
    "ceo_only": ceo_only,
    "keyword": keyword,
    "greedy": greedy,
    "greedy_90": partial(greedy, threshold=0.9),
    # Full engine (exact + partial edges + abstain) at three strictness presets.
    **{f"orgchart_{name}": partial(orgchart, exact_t=e, partial_t=p) for name, (e, p) in PRESETS.items()},
}
