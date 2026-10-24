"""Writes what each strictness preset costs, measured on dev, for the app's slider.

    uv run python -m orgchart.evaluation.run --engine orgchart_strict --split dev   # (and balanced, broad)
    uv run python -m orgchart.evaluation.presets
"""

import json
from pathlib import Path

from ..inference.engines import PRESETS

RUNS = Path(__file__).resolve().parents[2] / "runs" / "dev"
OUT = Path(__file__).resolve().parents[1] / "api" / "presets.json"
KEYS = ["precision", "wrong_per_1k", "exact_coverage", "useful_coverage", "ece"]


def main() -> None:
    out = []
    for name, (exact_t, partial_t) in PRESETS.items():
        m = json.loads((RUNS / f"orgchart_{name}.json").read_text())
        out.append({"name": name, "exact_threshold": exact_t, "partial_threshold": partial_t,
                    "measured_on": "dev", **{k: round(m[k], 4) for k in KEYS}})
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
