# Key decisions

A running log of design choices and why we made them. Feeds the final write-up.

## Phase 1: ground-truth generator

**Hybrid generation.** Code builds every org tree from industry templates
(departments, headcount shares, job ladders, span of control). Gemini runs once
to produce a vocabulary of real-world spellings per canonical role, cached to a
file. Structure stays valid and reproducible; titles get real-world variety.
Rejected: Gemini writing whole orgs (slow, costly, structurally unreliable).

**Realistic structural quirks in the truth.** Depth scales with company size;
skip-level reporting; reporting lines that depend on industry (Data under CTO /
CFO / COO, Security under CTO / CIO / CRO); regional sales splits; EAs and Chiefs
of Staff; flat partner structures; many same-title peer managers. Without these
the problem is trivially solvable from titles and the scores would mean nothing.

**Hidden clues, each with a reliability dial and a missing rate:**
- Office location (teams mostly co-located with their manager)
- Start date (managers usually joined first; teams hired in bursts)
- Team name in title ("EM, Payments" ↔ "Software Engineer - Payments")
- Previous employer (people follow managers between companies)

The dials let us measure how much each clue contributes to inference.

**Measurement built into the data.**
- Truth stored in a separate file the inference code never reads.
- Each company has a mess level (clean / medium / messy) to chart accuracy
  against data quality.
- Each true edge carries a "resolvable" label: could any clue in the flat data
  actually identify this manager? Abstaining on unresolvable edges is the
  correct answer, so "a wrong edge is worse than no edge" becomes measurable.
- Fixed random seed for a reproducible dataset.

**Scale: 500+ companies, 100 to 2,000 employees,** skewed towards smaller
companies (~200k people total). Big enough to be realistic, small enough to
generate in seconds and render in the app.

**Mostly Australian.** Firmable's market. Sydney / Melbourne / Brisbane / Perth
offices, ANZ and APAC regional roles, a minority of global firms with overseas
offices.

**Title vocabulary from Gemini, validated before use.** 268 canonical titles,
3,556 real-world spellings (`orgchart/generator/vocab.json`, committed so the
dataset rebuilds without an API key). LLM output can quietly change meaning, so
every variant is checked: it may not add a seniority word the canonical lacks
(EVP for VP, Lead for Manager), may not equal another canonical title (Chief Data
Officer for Head of Data), and a spelling offered for two levels is dropped for
both. ~10% were rejected; rejections are kept in the file for review. Head and
Director are treated as the same level, since real data swaps them freely.

**Free-tier Gemini, cheap models first.** Calls walk a fallback chain (Flash Lite
models first, bigger Flash models as backup) with a 90s timeout per call, because
the free tier often returns 503 "high demand" or hangs. Every response is cached on
disk, so reruns are free and deterministic.

## Phase 2: mess layer and dataset

**Two outputs, kept apart.** `people.csv` is what inference sees: one messy row
per record, shuffled opaque ids, no manager column. `truth/` is the answer key:
true manager, plus the list of mess types applied to each row, so accuracy can be
broken down by mess type.

**Missing managers resolve to the nearest visible boss.** If Raj -> Sara -> Tom
and Sara isn't in the data, the correct answer for Raj is Tom. That's what a
salesperson needs. These lines are flagged as skip-level and scored separately.

**Mess types.** Always on, scaled by mess level: vocabulary spellings, seniority
spellings, team-suffix formats, casing/typos, missing fields, unreliable
department field, acting/interim. Hard ones: missing employees, ghosts (left but
still listed; must never be anyone's manager), duplicates, LinkedIn fluff and
contractors, stale titles (promoted but profile shows old title), title inflation
(startup "VPs" running small teams), vague/creative titles, inconsistent location
and date formats.

**Mess levels per company: 20% clean, 50% medium, 30% messy.** Messy companies
get more of every mess type and weaker hidden clues, so we can chart accuracy
against data quality.

**600 companies** (~250k people), comfortably above the 500 minimum.

## Phase 3: title parsing and inference

**No peeking.** Inference code reads only the public files and may not import
anything from `orgchart/generator` (templates, vocabulary, team lists). A test
enforces it. Otherwise the parser would "know" the generator's vocabulary and
every score would be inflated.

**Honest splits.** Companies are split 360 train / 120 calibration / 120 test.
Weights are learned on train, confidences calibrated on calibration, and every
reported number comes from test companies the model never saw.

**Title parser: rules first, Gemini for the tail.** Normalise (strip fluff,
emojis, expand abbreviations), then keyword rules for seniority, department,
team qualifier and flags (contractor, acting, vague). Low-confidence titles go to
Gemini Lite in cached batches. Parser accuracy is measured on its own before the
engine is built on it.

**Inference: learned pairwise scores, assembled as a tree.** Candidate bosses are
more senior records in a compatible department. Each pair gets interpretable
features (level gap, department and team match, office, start-date order, shared
previous employer, department-field leak, ghost signals). A logistic regression
combines them; a maximum spanning arborescence picks everyone's manager jointly
so the result is a consistent tree.

**Three kinds of answer.** An exact edge with a confidence; a *partial edge*
("reports up to Tom, Senior EM"), used when the person is one of several
managers' reports and Tom sits above all of them, a true statement that answers
the economic-buyer question; or abstain. Partial edges are scored as ancestor
claims.

**Gemini as industry knowledge, for department heads only.** One prompt per
industry asks who each department head typically reports to (e.g. Head of
Security at a bank). Used as a prior feature for top-level lines; it draws on
Gemini's own knowledge, not on our generator.

**Gemini only where the rules are unsure.** Rule confidence below 0.7 is where the
rules are 0-57% right; above it they're 89-92% right. Routing only that tail sent
16,158 distinct titles (~118 calls, all on 3.5 Flash Lite) instead of 51k. Dev
split: level 86.8% -> 88.1%, department 88.7% -> 91.4%; creative titles 5% -> 41%
level. For vague titles the rule's industry default beats Gemini's guess.

**Independent check on the rules.** On 1,500 titles the rules parsed confidently,
Gemini (which never saw the generator) matches on department (93.7% vs 95.2%) but
trails on level (84.7% vs 94.0%), mostly on conventions like "HR Business Partner
is an IC". The rules encode those conventions deliberately, but they are also
traps the generator was built with, so the rules carry a few points of insider
advantage on seniority. Reported as such.

## Phase 3, piece 6: error analysis and fixes

**Every wrong edge gets a reason.** A diagnostic labels each wrong claim on dev by
cause, using the answer key: ghost given a boss, attached to a ghost, a look-alike
peer of the real boss, another branch of the same department, the real boss not
among the candidates, and so on. At the strict preset (486 wrong claims): ghosts
36%, wrong branch of the right department 24%, real boss not a candidate ~20%,
skip-levels (claimed a manager under the real boss) 17%.

**Fixed what the analysis pointed at.**
- Parser: inverted titles with the seniority word on the department ("Manager,
  Senior Engineering", "Officer, Chief Medical"), "Chf", "General Legal Counsel",
  "Area Retail Manager", "Group Product Manager". Level accuracy +0.3 points, and
  these are bosses, so it unblocks their reports.
- Candidates: execs always kept (a capped tier was dropping the CEO in big
  companies); a tier for closely related departments (Supply Chain under
  Operations, Merchandising under Store Ops); any manager when the person has no
  department. Recall of the real boss 82% -> 86% for 23% more pairs.
- Ghosts: an "older echo" signal. A record with the same department, level, team
  and previous employer as a colleague, but an earlier start, is what a stale
  profile looks like; 66-75% of such managers are ghosts. Feeds both the "none"
  option and the boss side.

**Result on dev.** Strict 88.1% -> 88.9% precision (7.8 wrong per 1k), balanced
83.7% -> 85.1%, broad 72.2% -> 74.3%; coverage unchanged or slightly up.

**What's left is mostly unrecoverable by design, and stays an abstain.**
- Most ghosts have no echo (no shared employer shown, or the original is hidden):
  they look exactly like staff.
- Choosing between several managers in one department when titles show no team
  and the office and start date don't separate them.
- Bosses with blank titles (about 2,100 dev lines) can't be placed by level; their
  reports fall back to a partial edge to the next visible boss.

**Tried and dropped: inferring a manager's team from their confident reports.** It
only touched 51 managers and moved nothing.

**Partial edges are under-confident, not over-confident.** Claims at 0.7-0.8 are
right 86-90% of the time, so the partial threshold is a safe dial.

## Phase 4: the web app

**One service.** FastAPI serves the API and the built React app from one place,
so there's one link and one deploy. The model, Gemini title parses and vocabulary
are committed; the dataset regenerates at build time (about 16s, no API calls).

**The engine stays in Python.** The server scores a company once (cached), then
assembles the chart at whatever strictness is asked for. Assembly is cheap, so the
slider is live without duplicating the logic in TypeScript.

**Collapsible tree, not boxes and lines.** Companies have 100-2,000 people; an
indented tree stays readable at that size and on a phone. Each line shows its kind
(exact, "reports up to", unplaced) and a confidence colour.

**Strictness is a slider.** Strict, balanced and broad, each labelled with the
precision and wrong edges per 1,000 measured on dev, so the user picks the
trade-off knowing what it costs.

**A "grade it" toggle.** The data is synthetic, so the app can mark each line right
or wrong against the answer key and show the company's scorecard. Reviewers can
check the confidences for themselves. Off by default; the inference never sees it.

**Per company:** a "why" panel (top candidate bosses with probabilities and the
clues behind them), people search, an unplaced list with reasons, and plain-English
questions answered by Gemini from the inferred chart (cached, rate-limited, Lite
models).

**One company in memory at a time.** All 600 companies plus the answer key take
over 1 GB; the free host has 512 MB. The dataset is split into
data/by_company/<id>/ (same layout as data/, so the same loaders work) and the
server scores a company on first open (0.2s typical, 2.4s for the largest) and
keeps the last 24. Peak about 300 MB.

**The app found a parser bug.** "Human Resources Partner" was read as a firm
partner (VP), so an HR team's reports were placed "up to" an IC. Fixed, tested,
model retrained; dev numbers unchanged within 0.1 points.
