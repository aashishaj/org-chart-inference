# Org Chart Inference

Infer who reports to whom from a flat list of employee profiles (name, job title,
department, office, start date, previous employer), with a confidence on every
reporting line, and leave a line blank when the evidence is weak.

> A wrong edge is worse than no edge.

**Live app:** https://org-chart-inference-kre5.onrender.com. Pick a company, slide
the strictness, click anyone to see why they were placed where they were, turn on
"Grade against the answer key" to see every line marked right or wrong, or ask a
question in plain English. It runs on Render's free plan: after 15 minutes idle
the first visit takes about a minute to wake it, and the first look at one of the
largest companies (1,900 people) takes up to 40 seconds to score.

Every view is a shareable link, for example
[Echidna Software, graded](https://org-chart-inference-kre5.onrender.com/?company=C0176&preset=balanced&grade=1).

## Results

Measured on the **test split**: 120 companies (56,840 records) that the
model never trained on and that no design choice was tuned on. They were scored
once, at the end.

| Engine | Precision | Wrong per 1,000 | Exact coverage | Useful coverage | Lines to a ghost |
|---|---|---|---|---|---|
| Baseline: everyone reports up to the CEO | 85.6% | 144.0 | 0.0% | 3.2% | 278 |
| Baseline: title keywords, nearest senior in department | 35.4% | 645.0 | 3.0% | 5.5% | 2,565 |
| Model, most likely boss if ≥ 50% (no "up to") | 73.4% | 38.3 | 11.2% | 11.2% | 186 |
| **Strict** | **90.9%** | **6.4** | 3.0% | 6.5% | 44 |
| **Balanced** | **86.1%** | **17.0** | 5.3% | 10.1% | 82 |
| **Broad** | **73.3%** | **57.0** | 11.5% | 14.8% | 209 |

- **Precision**: of the lines we drew, how many are right. A "reports up to X"
  line counts as right only if X really is above the person.
- **Wrong per 1,000**: wrong lines per 1,000 records. This is the number a sales
  team feels.
- **Exact coverage**: people with a manager whose direct manager we named.
- **Useful coverage**: exact, plus "reports up to X" where X is at most one level
  above their real manager.

What the numbers say:
- **The test split matches dev.** Strict went from 89.1% on dev to 90.9% on
  test, balanced from 85.0% to 86.1%, and broad from 74.0% to 73.3%. Tuning on dev
  didn't overfit it.
- **Precision alone can be gamed.** Saying everyone reports up to the CEO is 86%
  "precise", but it tells you nothing, and it gives ghosts a boss: 144 wrong lines
  per 1,000. That's why wrong-per-1,000 and useful coverage are the headline
  numbers.
- **Titles alone are wrong two times in three.** The obvious approach (keywords,
  then the nearest senior person in the department) draws 645 wrong lines per
  1,000. At strict, the model draws 6.4.
- **Coverage is low, and that's the data, not timidity.** In 78% of real reporting
  lines, the boss's true title is shared with another record in the same company
  (several Engineering Managers, several Store Managers). Titles can't separate
  them, and office, start date and team are each weak on their own. Where the
  evidence is there, the model uses it. Clean companies at broad get 28% useful
  coverage; messy companies at strict stay 85% precise.
- **By data quality:** strict precision is 96.1% on clean, 89.3% on medium and
  85.0% on messy companies.
- **Confidences mean what they say.** On test, the model's boss probabilities are
  off by 1.3 points on average (ECE). Lines it gives 90%+ are right 93% of the
  time, and 50–60% lines are right 56% of the time.

## How it works

### 1. A dataset with an answer key

There's no public dataset of real org charts, so the repo generates one:
600 Australian-flavoured companies across 10 industries, 100 to 1,900 visible
employees each, 293k profile records. Code builds each true org tree from
industry templates (departments, job ladders, span of control, skip-levels, EAs,
regional sales splits, flat partnerships). A "mess layer" then flattens it into
what a data provider actually sees: 87k distinct title spellings (a Gemini-made
vocabulary of real-world variants, validated so no variant changes seniority),
typos, LinkedIn fluff, blank fields, stale profiles of people who left
("ghosts"), duplicates, people missing from the data, and inflated titles. Each
company gets a mess level (clean, medium, messy).

The answer key goes to `data/truth/`, which inference code is not allowed to read.
A test enforces it (`tests/test_no_peeking.py`). The generator is seeded: the
same command always produces byte-identical data, so the data isn't committed.
See [docs/dataset.md](docs/dataset.md) for how messy it is and how strong each
clue is.

### 2. Reading titles

Rules first: normalise (fluff, emoji, abbreviations, inverted titles like
"Manager, Senior Engineering"), then read seniority (CEO … Junior), department
and team. About 16k titles the rules aren't sure about (confidence below 0.7,
where the rules are 0–57% right) go to Gemini Flash Lite in cached batches.
Gemini lifts level accuracy from 86.8% to 88.1% and department accuracy from
88.7% to 91.4% on dev, and reads creative titles far better (seniority right
for 41% of them, against 5% for the rules). Its answers are committed, so the app never needs a key to
score.

### 3. Candidate bosses and clues

For each person, candidates are more senior records, in tiers: the nearest
manager level in their department, the rest of their department, the execs, and
managers in related departments. Each pair gets interpretable features:
- **Seniority:** level gap.
- **Fit:** department and team match, and a department-pair prior learned on train.
- **Clues:** same office, start-date order, joined within 6 months of the boss,
  shared previous employer, and the department field naming the boss's
  department.
- **Ghost signs:** an older copy of a current role, or the earliest of several
  look-alike roles.
- **Top of the company:** "C-suite reports to the CEO".

### 4. Probabilities, including "none of these"

A conditional logit gives a probability to every candidate *and* to "none of
these". "None" is right for ghosts, the CEO, and people whose boss isn't in the
data, so the model learns when not to answer. The weights are trained on the
train split (`orgchart/evaluation/train.py`) and committed as
`orgchart/inference/model.json`.

### 5. Three kinds of answer

- **Exact:** the most likely boss clears the threshold. "Reports to Min-jun Han, 93%."
- **Up to:** no single boss is likely enough, but someone is very likely *above*
  them. For example, the person could report to any of three Engineering Managers
  who all sit under the same Head of Engineering. The probability that A is
  somewhere above the person is summed over all routes (exact in one pass, because
  bosses are always more senior). The claim is "reports somewhere under X". It is
  never "up to the CEO", since everyone is.
- **Not placed:** neither is likely enough, or "none of these" wins. The app still
  shows the best guess and why it wasn't enough.

The strictness setting is just the two thresholds: strict (exact ≥ 0.9, up to
≥ 0.8), balanced (0.8 / 0.7) and broad (0.5 / 0.6). The app labels each with its
measured precision, so the user picks the trade-off knowing the cost.

## How success was measured

- **Every record gets exactly one outcome.** It is one of: exact right, exact
  wrong, up-to right, up-to wrong, a line for someone with no boss in the data,
  left out but had a boss, or rightly left out
  (`orgchart/evaluation/scorecard.py`). Leaving a ghost blank is a correct answer,
  and attaching anyone to a ghost is a wrong one.
- **The scorecard can't be gamed with vague answers.** "Reports up to the CEO" is
  never useful coverage, and the `ceo_only` baseline proves it.
- **Splits are by company:** 360 train / 120 dev / 120 test, stratified by
  industry. Train fits the weights, dev was used for every decision, and test was
  scored once.
- **Error analysis by cause.** On dev, each wrong line was labelled using the
  answer key: ghost given a boss, wrong branch of the right department, real boss
  not among the candidates, skip-level. The biggest causes were then fixed in the
  parser, the candidate tiers and the ghost detection
  ([docs/decisions.md](docs/decisions.md)).
- **Calibration.** The model's boss probabilities are off by 3.6 points on
  average on dev, and 1.3 on test (ECE). "Up to" lines are under-confident (claims at 70–80% are right
  86–90% of the time), so the thresholds are on the safe side.
- **An independent check on the title rules.** I wrote the rules after seeing the
  generator's spellings, so they could be "cheating". On 1,500 titles, Gemini
  (which never saw the generator) agrees on department (93.7% vs 95.2%) but
  trails on seniority (84.7% vs 94.0%), mostly on conventions like "HR Business
  Partner is an IC". So the rules carry a few points of insider advantage on
  seniority, reported as such.

## Where AI does the work

- **Generating realistic mess:** Gemini wrote 3,556 real-world spellings for 268
  roles. Code validated them, rejecting about 10% that changed meaning.
- **Reading the long tail of titles:** Gemini handles only what the rules are
  unsure of, in cached batches, and is allowed to answer "can't tell".
- **Ask in plain English:** Gemini answers questions like "Who reports to the
  CFO?" or "Which managers have the biggest teams?" with four lookup tools over
  the chart on screen. It must cite people (`[[id|Name]]`), and any id no tool
  returned is unlinked. It gives confidences, keeps "somewhere under" distinct
  from "reports to", and never sees the answer key. Answers are cached and
  rate-limited (8 per visitor per 10 minutes, 300 a day), because the hosted app
  spends one key.

## What's hard, and left blank on purpose

- **Most ghosts look exactly like staff.** A stale profile with no newer holder of
  the same role, and no shared employer, is indistinguishable from a real
  employee.
- **Look-alike managers.** Several Engineering Managers in one office, hired the
  same year, with no team in anyone's title. That's what "reports up to the Head
  of Engineering" is for.
- **Blank or unreadable boss titles** can't be placed by seniority, so their
  reports fall back to the next visible boss.
- **Typos in titles.** "Senior Legal Conusel" isn't read as counsel, and its
  reports go elsewhere.
- **Simplifications in the data:** one manager per person (no dotted lines), one
  snapshot in time, a single CEO per company.

## Run it

```bash
uv sync                                          # Python 3.12 deps
uv run python -m orgchart.generator.generate     # data/ (about 20s, no API key)
uv run python -m orgchart.api.store              # per-company split for the app
cd web && npm install && npm run build && cd ..
uv run uvicorn orgchart.api.app:app --port 8000  # http://localhost:8000
```

For the "Ask" box, copy `.env.example` to `.env` and add a `GEMINI_API_KEY`.
Without one the box is hidden; everything else works.

For frontend work, run `npm run dev` in `web/`; it proxies `/api` to port 8000.

```bash
uv run pytest                                                          # 514 tests
uv run python -m orgchart.evaluation.run --engine orgchart_strict      # dev scorecard
uv run python -m orgchart.evaluation.run --engine all --split test     # final numbers
uv run python -m orgchart.evaluation.train                             # retrain model.json
```

## Deploy

`render.yaml` is a Render Blueprint for one Docker web service. The
`Dockerfile`:
- builds the React page;
- installs the Python app;
- regenerates the dataset and splits it per company.

FastAPI serves both the API and the page. It fits Render's free 512 MB instance:
it keeps up to 4,000 scored records in memory, and the worst case measured was
294 MB. On Render, go to New → Blueprint, pick this repo, and paste a
`GEMINI_API_KEY` when asked. The key is optional.

## Layout

```
orgchart/
  generator/    true org trees, the mess layer, the answer key
  inference/    title parsing, candidate bosses, the model, assembly
  evaluation/   splits, training, scorecard, error analysis
  api/          FastAPI: companies, charts, why, grade, ask
  llm.py        Gemini wrapper (model fallbacks, disk cache)
web/            React + Vite page (no UI libraries)
docs/           decisions.md (design log), dataset.md (dataset report)
tests/          pytest, including the no-peeking test
```
