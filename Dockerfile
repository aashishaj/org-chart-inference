# One service: FastAPI serves the API and the built React page.
# The dataset isn't in git (over 1 GB with the answer key); the generator is seeded,
# so the build regenerates the identical data in about 20 seconds.

# -- the page -----------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# -- the app ------------------------------------------------------------------------
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 MALLOC_ARENA_MAX=2

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY orgchart ./orgchart
RUN uv sync --frozen --no-dev

# Generate the 600 companies, split them per company for the app, then drop the
# full-size files: the app only reads data/by_company/.
RUN uv run --no-sync python -m orgchart.generator.generate \
 && uv run --no-sync python -m orgchart.api.store \
 && rm -f data/people.csv data/truth/people.csv data/truth/true_tree.csv

COPY --from=web /web/dist ./web/dist

# GEMINI_API_KEY is optional: without it the "ask" box is hidden.
CMD ["sh", "-c", "uv run --no-sync uvicorn orgchart.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
