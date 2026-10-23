"""Inference must only see what a real data provider would see. If inference code
imported the generator (templates, vocabulary, team lists) or read the answer key,
every score we report would be inflated. This test fails the build if it does."""

import ast
from pathlib import Path

INFERENCE = Path(__file__).resolve().parents[1] / "orgchart" / "inference"
FORBIDDEN_MODULES = ("generator", "evaluation")


def _sources():
    files = sorted(INFERENCE.rglob("*.py"))
    assert files, "no inference code found"
    return [(f, ast.parse(f.read_text())) for f in files]


def test_inference_never_imports_generator_or_evaluation():
    for path, tree in _sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = [mod] + [f"{mod}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                continue
            for name in names:
                parts = name.split(".")
                assert not any(p in FORBIDDEN_MODULES for p in parts), f"{path.name} imports {name}"


def test_inference_never_mentions_the_answer_key():
    for path, tree in _sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "truth" not in node.value.lower().replace("ground truth", ""), \
                    f"{path.name} references {node.value!r}"
