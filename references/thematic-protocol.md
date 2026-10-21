# Module T — Thematic Deep Research

For a **topic**, not a ticker: "is private credit overheating", "India's EV
supply chain", "what happens to NBFC margins if rates fall 200bp", "the
economics of grid-scale storage".

Produces `research-<slug>.pdf` — a report with charts, a key-findings strip,
a tabulated comparison of published estimates, and a complete source log.

Report and analyse only. Do not express a view on what the reader should do.
No price targets, no "the opportunity is attractive", no implied trade.

---

## Why this runs in phases

One pass of searching against a fixed template produces a literature summary:
accurate, shallow, and indistinguishable from the first page of results. The
phases exist to force three things that a single pass skips — **working out
what the real question is before researching it**, **finding where informed
people actually disagree**, and **going deep only where depth changes the
answer**.

Each phase has a gate. Do not start the next phase until the gate is met. The
gates are the whole point: without them this collapses back into one pass.

---

## Phase 1 — Scope

Cheap, broad, and deliberately shallow. You are mapping the territory, not
researching it.

1. **Restate the question** in one sentence, as a question with an answer. "Is
   private credit overheating" becomes "have underwriting standards,
   leverage and spreads in direct lending deteriorated enough to produce
   losses materially above the last cycle". If the user's phrasing is vague,
   state the reading you took and continue — do not stop to ask.
2. **Decompose into 4–8 sub-questions** that together answer it. Each must be
   answerable with evidence, not opinion. "Is it a bubble" is not a
   sub-question; "how have loan-to-value ratios moved since 2021" is.
3. **Identify the quantities** the answer turns on — market size, growth
   rate, margin, default rate, capacity, penetration. Note which are
   *measured* (someone counts them) and which are *estimated* (someone
   models them). These are different kinds of number and Phase 4 treats them
   differently.
4. **Name the actors**: who publishes data here, who regulates, who has an
   interest in the number being high or low. A market-size estimate from a
   firm that sells into that market is still usable; its provenance is part
   of the finding.
5. **Scan 6–12 sources** broadly — one search per sub-question. Read titles
   and leads, not whole documents. The purpose is to learn what exists and
   where the data lives.

**Gate 1.** Written in the bundle: the restated question, the sub-questions,
the quantity list split into measured and estimated, and for each
sub-question either a named source type that will answer it or a note that it
may not be answerable. If more than half the sub-questions have no identified
source, the question as posed may not be researchable — say so in the report
rather than padding it.

---

## Phase 2 — Map the disagreement

The phase that separates research from summarising. You are looking for the
places where competent, informed people reach different conclusions from the
same facts, because that is where the answer actually lives.

1. **Find the competing positions.** For each major claim, who argues the
   other side, and on what grounds? Not "some analysts are cautious" — the
   named party, their stated reason, their number.
2. **Locate the disputed variable.** Disagreements in finance almost always
   reduce to one or two quantities: a growth rate, a default assumption, a
   terminal share, how a cost curve bends. Name it explicitly. If two parties
   forecast the same market at $20bn and $47bn, something specific differs —
   definition, geography, base year, or a growth assumption — and finding
   which is more valuable than quoting both.
3. **Separate definitional from substantive disagreement.** A large share of
   apparent conflict is two people measuring different things. Check the
   definitions before concluding anyone is wrong.
4. **Note what would settle it.** For each live disagreement, what evidence
   would resolve it, and does that evidence exist? "A regulator's loan-level
   data, not published" is a finding.

**Gate 2.** At least two genuine disagreements identified with named parties
and the specific disputed quantity, **or** an explicit statement that the
field is in consensus with the evidence for that claim. A report that finds
no disagreement anywhere has usually not looked.

---

## Phase 3 — Deep dive

Now go deep, and only where Phase 2 showed it matters. A uniform 500 words
per sub-question is a worse report than 2,000 on the two that decide the
answer and 200 on the rest.

1. **Prioritise.** Rank the sub-questions by how much the overall answer moves
   with them. Spend accordingly, and say in the report where you went deep
   and where you did not.
2. **Primary sources only for load-bearing facts.** Regulator publications,
   central bank data, company filings, official statistics, the actual paper
   rather than coverage of it. Press is for finding events, never for
   carrying a number.
3. **Get the series, not the sentence.** Where a claim is about a trend, find
   the underlying data series and extract it into the bundle. A chart needs
   numbers; a quoted percentage does not become a chart.
4. **Date everything and check vintages.** A 2023 forecast of 2026 can now be
   scored against what happened — do that, it is one of the most informative
   things a report can contain.
5. **Follow the chain.** When a figure is cited, find who produced it. Three
   sources quoting one original is one source, and Phase 4 will catch it if
   you record the chain.

**Gate 3.** Every load-bearing claim has a primary source with a date. Every
chart has its series in the bundle with per-point provenance. At least one
prior forecast scored against outturn, where the topic has any history.

---

## Phase 4 — The estimate layer

Where "the market will reach $X by 2030" gets handled honestly. This is a
distinct phase because published forecasts are not facts and must not be
reported as though they were.

Run the engine:

```bash
python3 scripts/estimate_core.py bundle.json --report
```

For every estimate, the bundle records: **who** produced it, **when** (the
publication date, not the forecast date), the **base year and base value**,
the **target year and value**, the **method** if stated, and the
**upstream source** if it is restating someone else's work.

The engine then:

- **Recomputes the implied CAGR** from base and target, and compares it with
  any growth rate the source states. These disagree more often than you would
  expect, and when they do, one of the published numbers is wrong.
- **Reports the spread** — range, median, and the ratio of high to low. A
  market where published forecasts span 2.5x is a market nobody can size, and
  that is the finding; picking the middle one hides it.
- **Flags shared ancestry.** Estimates tracing to one upstream source are not
  independent corroboration, however many outlets carry them. The engine
  groups by `upstream` and tells you how many genuinely independent estimates
  you have. Often it is one.
- **Flags stale vintages** — a forecast whose base year is now in the past can
  be checked against outturn, and should be.
- **Flags definitional mismatch** where scope or geography differ, so they are
  not averaged together as if comparable.

**Never average published forecasts into a single number.** Report the range
with each estimate attributed, and say which you find most credible and why —
"most credible" being a judgement about method and independence, not a
prediction.

**Gate 4.** Every estimate in the report carries full provenance. The spread
is stated. The independence count is stated. No estimate appears as a bare
number in prose without its author and date.

---

## Phase 5 — Synthesise and visualise

### Citations are numbered and inline

Every factual sentence in the body carries a bracketed marker — `[3]`,
`[7, 12]` — resolving to the numbered reference list at the back. This is not
decoration: it is what lets a reader check any single claim without reading
the whole source log, and it is the standard every serious research
publisher holds to.

The rules the audit enforces:

- **Every number, quote and attributed claim carries a marker.** A figure in
  prose without one is a defect, exactly as it is in Module R.
- **Every marker resolves** to a source in the bundle's `sources` list.
  A dangling `[14]` with thirteen sources fails the build.
- **Every source is cited at least once.** An uncited source in the list is
  padding — either cite it or remove it.
- **Numbering is contiguous from 1**, assigned in order of first appearance,
  so the reader can scan the list in the order the report uses it. The
  builder assigns the numbers; you write `[S:imf-weo-2026]` style keys in
  the bundle and it resolves them. Writing raw numbers by hand guarantees
  they drift when a section moves.
- **Charts cite too.** Each chart's caption carries the markers for the
  series it draws.

### Writing standard

The prose is the deliverable, not a wrapper around the charts. What
distinguishes a senior analyst's report:

- **The answer first.** Conclusion in the first 150 words, then the evidence
  for it. A report whose conclusion is on page nine has failed.
- **Claims are specific and falsifiable.** Not "growth is expected to be
  strong" but "three of four published forecasts imply 11–14% CAGR to 2030,
  the fourth 4%, and the difference is entirely a terminal-penetration
  assumption [4, 6, 9, 11]".
- **Disagreement is foregrounded, not smoothed.** Where sources conflict, say
  so in the body with both numbers and both authors, and say which you find
  better-founded and on what methodological grounds.
- **Confidence is marked per finding** — well-evidenced, contested, or thin.
  Uniform confidence tells the reader nothing about reliability.
- **No hedging filler.** "It is important to note", "the landscape is
  complex", "various factors" — cut all of it. If a sentence survives
  deleting its qualifiers, delete the qualifiers.
- **No recommendation**, however the prose tempts toward one.

1. **Answer the question asked**, in the first 150 words, in prose a busy
   reader can act on. Then the evidence.
2. **State confidence honestly per finding** — well-evidenced, contested, or
   thin. A report with uniform confidence is not telling you anything about
   its own reliability.
3. **Charts earn their place.** Each must make a point the prose cannot make
   as quickly. The chart engine handles the drawing:

   ```bash
   python3 scripts/research_charts.py bundle.json --outdir charts/
   ```

   Available forms: `timeseries` (a trend), `estimate_range` (the spread of
   published forecasts, which is the signature chart of this module),
   `composition` (shares of a whole), `bars` (comparison across categories),
   `waterfall` (what builds to a total). Each chart is drawn from a series in
   the bundle and ships with its data table beneath it, so no figure in the
   report is unsourced and the charts stay readable in print and for
   colour-blind readers.
4. **The key-findings strip** at the top: three to five findings, each one
   line, each with its confidence. This is the infographic element that gets
   read when nothing else is.
5. **Build and audit:**

   ```bash
   python3 scripts/build_report.py bundle.json -o research-<slug>.pdf
   python3 scripts/audit_research.py bundle.json --pdf research-<slug>.pdf
   ```

**Gate 5.** The audit exits 0: every citation marker resolves, every source
is cited, the answer is in the first 150 words, every chart's data is in the
bundle, every section carries a confidence marker, and no sentence recommends
an action.

---

## What this module will not do

- **Predict.** It reports what others forecast, with provenance and spread,
  and scores past forecasts against outturn. It does not add a forecast of
  its own unless the user explicitly asks for a bottom-up estimate, in which
  case the method is shown and labelled as the skill's own construction.
- **Resolve a disagreement the evidence does not resolve.** "Both positions
  are internally consistent and the deciding data is not public" is a
  legitimate conclusion and a more useful one than a fabricated verdict.
- **Fill a section because the template has a heading.** An empty section
  with "no reliable data found, here is where I looked" is correct.
- **Recommend.** Not what to buy, not what to build, not what to do.
