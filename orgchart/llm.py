"""Thin wrapper around Gemini. Everything LLM-related goes through here so we can
cache responses and swap models in one place.

Every response is cached on disk (keyed by model + prompt), so re-running the
generator or an eval costs nothing and returns identical results.

The free tier is often overloaded (503s) or very slow, so calls walk a fallback
chain of models and give up on a model that hangs.
"""

import hashlib
import json
import os
import time
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

# First model is preferred; the rest are fallbacks when it's overloaded or hanging.
# Lite models first: on the free tier they have the most generous limits, and our
# tasks (title variants, title parsing) are simple; outputs are validated anyway.
MODELS = os.getenv("GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-flash-lite-latest,gemini-3.1-flash-lite,"
                   "gemini-3.5-flash,gemini-2.5-flash").split(",")
MODEL = MODELS[0]
TIMEOUT_S = 90
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "llm"

models_used: set[str] = set()  # which models actually answered this run (for provenance)


@cache  # one long-lived client; a throwaway one gets closed before the request is sent
def client() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing: copy .env.example to .env and add your key")
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_S * 1000))


def _path(model: str, kind: str, prompt: str) -> Path:
    return CACHE_DIR / f"{hashlib.sha256(f'{model}|{kind}|{prompt}'.encode()).hexdigest()}.txt"


def _generate(kind: str, prompt: str, config: types.GenerateContentConfig | None = None) -> str:
    for model in MODELS:  # any model's cached answer will do
        if (p := _path(model, kind, prompt)).exists():
            models_used.add(model)
            return p.read_text()
    last_error = None
    for round_ in range(3):
        for model in MODELS:
            try:
                text = client().models.generate_content(model=model, contents=prompt, config=config).text
            except errors.APIError as e:
                if e.code not in (429, 500, 503, 504):
                    raise
                last_error = e
                continue
            except Exception as e:  # timeouts surface as httpx errors
                if "timed out" not in str(e).lower() and "timeout" not in type(e).__name__.lower():
                    raise
                last_error = e
                continue
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _path(model, kind, prompt).write_text(text)
            models_used.add(model)
            return text
        time.sleep(20 * (round_ + 1))  # every model busy: wait, then try the chain again
    raise RuntimeError(f"all Gemini models unavailable: {last_error}")


def ask(prompt: str) -> str:
    return _generate("text", prompt)


def ask_json(prompt: str):
    return json.loads(_generate("json", prompt, types.GenerateContentConfig(response_mime_type="application/json")))


if __name__ == "__main__":
    # Smoke test: `uv run python -m orgchart.llm`
    print(ask("Normalise this job title to 'level | function': 'Snr Mgr, Data & Analytics'"), models_used)
