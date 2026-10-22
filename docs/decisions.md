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
