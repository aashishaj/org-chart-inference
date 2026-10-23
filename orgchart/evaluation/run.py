"""The dev loop: run an engine on a split, print its scorecard and the change since
the last run of the same engine.

    uv run python -m orgchart.evaluation.run --engine keyword            # dev split
    uv run python -m orgchart.evaluation.run --engine all --split test  # final numbers

Each run is saved to runs/<split>/<engine>.json so the next run can show deltas.
"""

import argparse
import json
import time
from pathlib import Path

from ..inference.data import DATA_DIR, load_companies
from ..inference.engines import ENGINES
from .scorecard import format_report, load_truth, score
from .split import SPLITS, companies_in

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"


def evaluate(engine: str, split: str = "dev", data_dir: Path = DATA_DIR, save: bool = True) -> dict:
    ids = set(companies_in(split, data_dir))
    companies = load_companies(data_dir)
    truth = load_truth(data_dir, ids)
    t0 = time.time()
    preds = [p for cid in sorted(ids) for p in ENGINES[engine](companies[cid])]
    metrics = score(preds, truth) | {"engine": engine, "split": split, "seconds": round(time.time() - t0, 1)}
    path = RUNS_DIR / split / f"{engine}.json"
    previous = json.loads(path.read_text()) if path.exists() else None
    print(format_report(engine, split, metrics, previous))
    if save:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metrics, indent=1))
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Score an inference engine against the answer key.")
    ap.add_argument("--engine", default="keyword", choices=[*ENGINES, "all"])
    ap.add_argument("--split", default="dev", choices=SPLITS)
    args = ap.parse_args()
    for name in ENGINES if args.engine == "all" else [args.engine]:
        evaluate(name, args.split)
