"""Thin wrapper around Gemini. Everything LLM-related goes through here so we can
cache responses and swap models in one place."""

import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def client() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing: copy .env.example to .env and add your key")
    return genai.Client(api_key=key)


def ask(prompt: str) -> str:
    return client().models.generate_content(model=MODEL, contents=prompt).text


if __name__ == "__main__":
    # Smoke test: `uv run python -m orgchart.llm`
    print(ask("Normalise this job title to 'level | function': 'Snr Mgr, Data & Analytics'"))
