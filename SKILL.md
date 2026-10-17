---
name: financopedia
description: End-to-end finance workflow — market research, formula-driven Excel models (DCF, three-statement, LBO, IPO), and earnings-call review, each gated by an automated audit. Use when the user asks for financial research on a company, a valuation or DCF, a full breakdown of a company's financials, an LBO or buyout return, an IPO pricing, an earnings call review, a company brief, or comparables. Triggers on "research [TICKER]", "build a model for", "value this company", "what would it price at", "LBO this", "break down their financials", "review the earnings call", "financopedia". Research and analysis only — never produces buy/sell recommendations.
---

# Financopedia

A three-module equity research pipeline that runs start to finish without
check-ins, and gates its own output through automated verification before
delivery.

**Hard rule, applies to every module and every output:**
Report and analyse only. Do not express a view on what the user should do.
No buy/sell/hold, no price targets of your own, no "attractive entry point".
If a sentence could be read as advice, delete it. You are not a licensed
advisor and nothing produced here is financial advice — state this once, in
the delivery message, not on every page.

---

## 1. Route the request

Read what the user asked for and pick modules. Do not ask which they want —
infer, state the inference in one line at the start of the run, and proceed.

| What the user asked for | Modules to run |
|---|---|
| "research X", "what's going on with X", "brief me on X" | R |
| "build a model / DCF / value X" | R → M(`dcf`) |
| "break down their financials", "full operating model", "forecast the accounts" | R → M(`statements`) |
| "could PE buy this", "LBO it", "sponsor returns" | R → M(`statements`) → M(`lbo`) |
| "what would it IPO at", "price the float" | R → M(`statements`) → M(`ipo`) |
| "review the Q3 call", transcript attached | E (R only if no prior context on file) |
| "full workup", "everything on X", vague/ambitious | R → M(`dcf`) → M(`statements`) → E |
| "update X" and a `notes/<TICKER>.md` exists | read notes → R (delta only) → E |

R = Research · M = Model (four types) · E = Earnings review.
When in genuine doubt, run more rather than fewer — the pipeline is
automated, extra modules cost time not attention.

The four model types — `dcf`, `statements`, `lbo`, `ipo` — are chosen in
`references/model-protocol.md`. All four demand **7 to 12 years of history**
and refuse to build on less; the reason is in that file.

Create a task list for any run with two or more modules so the user can
follow progress while away.

---

## 2. Run the modules

Each module has its own protocol file. **Read the protocol before starting
that module**, not before — opening all three up front wastes context and
pulls the research toward the model's shape.

| Module | Protocol | Produces |
|---|---|---|
| Research | `references/research-protocol.md` | `research-<TICKER>.md` |
| Model | `references/model-protocol.md` | `<TICKER>-<type>.xlsx` + assumption memo |
| Earnings | `references/earnings-protocol.md` | `earnings-<TICKER>-<Q>.md` |

They chain: the model's INPUTS come from figures the research module
sourced, and the earnings review tests the thesis recorded in notes.

### Evidence rules (all modules, non-negotiable)

1. **Every figure carries a source and a date.** Format:
   `$4,210m (FY2025 10-K, filed 2026-02-14)`. A figure without one does not
   go in the output — not in a footnote, not "approximately". Drop it and
   say what is missing.
2. **Label inference.** Anything you worked out rather than read is prefixed
   `INFERENCE:`. Anything you could not confirm is
   `COULD NOT VERIFY: <what, and where you looked>`.
3. **Prefer primary.** Filings and transcripts over press coverage, press
   coverage over aggregators, never forums. Fetch the filing itself; do not
   rely on recall for any number.
4. **Check the date on everything.** Your knowledge has a cutoff and filings
   move. Search for the current state, then open the source. A figure whose
   as-of date you cannot establish is unverified.
5. **Never fabricate to fill a template section.** An empty section with
   "no disclosure found" is a correct answer. An invented one is a failure
   of the whole run.

---

## 3. Verify before delivering

This is what makes the pipeline trustworthy, and it is not optional. Run
every gate that applies. A failing gate is fixed and re-run, not explained
away.

### Gate 1 — model integrity (automated)

```bash
python3 scripts/audit_model.py <TICKER>-<type>.xlsx --spec SPEC.json --type <type>
```

Recalculates the workbook headlessly through LibreOffice and compares every
output against an independent engine recomputed in Python from the same
spec — the two implementations were written separately, so a transcription
error surfaces as a mismatch rather than a plausible wrong number. It also
proves: no hardcoded constants outside INPUTS/HISTORICALS, every calculation
cell is a formula, the sensitivity grid is driven off the inputs, no broken
references, every historical figure sourced, every assumption with a basis,
and the forecast drivers inside the historical range.

Each type adds the identity that matters for it: the balance sheet balances
every year (`statements`), sources equal uses and the value attribution is
exact (`lbo`), post-money value per share equals the offer price and the use
of proceeds reconciles (`ipo`), the sensitivity centre equals the base case
(all four).

Exit code 0 = ship. Non-zero = fix and re-run. Do not hand over a workbook
that has not exited 0. The gates have been tested against deliberate
sabotage — a hardcoded cell, a dropped balance-sheet line, interest charged
on closing balances, a missing net-debt deduction — and caught all of them.

### Gate 2 — citation integrity (automated)

```bash
python3 scripts/audit_report.py research-<TICKER>.md
```

Flags any sentence containing a figure that lacks an adjacent source and
date, any unlabelled estimate, and any recommendation language
("we like", "attractive", "should buy", "undervalued", a target price).
Fix every hit. Re-run until clean.

### Gate 3 — adversarial read (fresh agent)

Spawn a subagent that has **not** seen the work being produced, give it only
the deliverables and `references/verification.md`, and have it try to break
them: trace three figures back to their cited source, check the arithmetic
of the valuation bridge independently, and hunt for recommendation drift.
Its findings are acted on before delivery; unresolved ones are disclosed in
the delivery message.

### Gate 4 — honest confidence statement

Every delivery ends with a short verification block:

```
Verification: model audit PASS (14/14 checks) · citation audit PASS ·
adversarial review PASS with 1 note. 23 of 25 figures traced to primary
filings; 2 marked COULD NOT VERIFY (see report §4).
```

Never claim a confidence level the gates did not establish. "100% verified"
is a claim about the checks that ran, not about the future — the gates prove
internal consistency and sourcing, they cannot prove a filing was honest or
a projection will hold. Say what was checked.

---

## 4. Persistent company notes

The compounding asset. Keep `notes/<TICKER>.md` using
`templates/notes-template.md`. On any run for a company that already has a
notes file, **read it first**: the earnings module tests the recorded thesis
against the call, and the research module reports only what changed.

After every run, update the file: what moved, what is still open, date it.
Never edit the user's three-sentence view — that is theirs. Append what the
evidence did to it.

---

## 5. Working unattended

The user has asked not to be interrupted. Therefore:

- Do not ask clarifying questions mid-run. Take the most reasonable reading,
  state it in the opening line, and proceed.
- Missing data is reported, not guessed at. If the ticker is ambiguous, pick
  the largest listing matching the name, say so, and continue.
- If a source is unreachable, try one alternative route, then record
  `COULD NOT VERIFY` and move on. Do not stall the run on one figure.
- Deliver files as they finish rather than batching to the end, so the user
  can redirect early.
- The only thing that stops the run: a request that would require expressing
  a view on what to buy or sell. Produce the analysis without it and note
  the omission.
