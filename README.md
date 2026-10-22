# Org Chart Inference

Turn a flat list of employees and job titles into an inferred org chart, with a
confidence on every reporting line, and abstain where the evidence is weak.

> A wrong edge is worse than no edge.

## Layout

```
orgchart/
  generator/    ground-truth org trees + the "mess layer" that flattens them
  inference/    title parsing + manager inference
  evaluation/   scores inference against the hidden ground truth
  api/          FastAPI backend serving companies and charts
  llm.py        Gemini wrapper (title parsing long tail)
web/            React + Vite frontend
data/           generated datasets (gitignored, rebuilt by the generator)
docs/           write-up and dev log
```

## Setup

```bash
cp .env.example .env        # add your GEMINI_API_KEY
uv sync                     # Python deps
uv run python -m orgchart.llm   # smoke-test Gemini
cd web && npm install && npm run dev
```

## Plan (5 days)

| Day | Phase | Done when |
|-----|-------|-----------|
| 1 | Ground-truth generator + mess layer | 500+ companies, true tree saved separately from the messy flat list |
| 2 | Title parser (rules + Gemini fallback) | Parser accuracy measured against the generator's true titles |
| 3 | Inference engine + evaluation harness | Precision / recall / calibration report per run |
| 4 | Web app (chart, confidence, "why", sales queries) | Pick a company, see its chart locally |
| 5 | Deploy, write-up, polish | Public link + this README finished |
