"""Registry of inference engines. Each takes one Company and returns one Prediction
per record."""

from collections.abc import Callable

from .baselines import ceo_only, keyword
from .data import Company, Prediction

ENGINES: dict[str, Callable[[Company], list[Prediction]]] = {
    "ceo_only": ceo_only,
    "keyword": keyword,
}
