# Verification

The pipeline runs unattended, so the checks have to be mechanical rather
than a matter of care. Nothing here relies on the producing agent judging
its own work.

## What "high confidence" actually means here

The gates prove **internal consistency and provenance**: every figure traces
to a document, the workbook computes what it claims to compute, and the
output contains no advice. They cannot prove a filing was honest, a
projection will hold, or that a material fact was not simply absent from
every source searched. Claim what was checked, never more.

The useful promise: *if the sources are right, the output is right, and you
can see every source.* That is the part that can be driven close to 100%,
and the gates below are how.

## Gate 1 — model integrity

`scripts/audit_model.py` is type-aware. Common to all four model types:

1. Spec validates — 7-12 years of history, a source on every historical
   figure, a basis on every assumption.
2. All required tabs present.
3. No hardcoded numbers anywhere on the calculation sheets.
4. Every calculation cell is a formula (the projection, the bridge, the
   statements, the debt schedule, the offering build-up).
5. The sensitivity grid is formula-driven off INPUTS.
6. INPUTS and HISTORICALS match the spec cell for cell.
7. The workbook recalculates in LibreOffice without error.
8. No `#REF!`, `#DIV/0!` or other error values anywhere.
9. **Outputs match an independently written Python engine**, line by line.
10. The in-workbook CHECKS tab reads PASS on every row.
11. The sensitivity centre equals the base case, and the grid actually varies.
12. Forecast drivers sit inside the historical range (REVIEW, not FAIL, when
    they do not — it needs a reason, not suppression).

Check 9 is the one that matters most: the Excel formulas and the Python
engine were written separately from the same spec, so agreement to within
1e-6 means a transcription error in either would have surfaced.

Then each type adds the identity that cannot be fudged:

| Type | The identity |
|---|---|
| `dcf` | EV = PV of explicit FCF + PV of terminal value; equity = EV less net debt |
| `statements` | Assets = liabilities + equity in **every** year, reported and forecast; closing cash ties to the cash flow statement; equity and PP&E roll forward correctly |
| `lbo` | Sources = uses exactly; EBITDA growth + multiple change + debt paydown = change in equity value, to the cent; (1+IRR)^years = money multiple |
| `ipo` | Post-money value per share = offer price; pre-money + proceeds = post-money; use of proceeds reconciles to net primary |

### These gates have been tested by sabotage

Checks that never fail prove nothing, so each was run against a deliberately
corrupted workbook:

| Sabotage | Caught by |
|---|---|
| A hardcoded value in the projection | Hardcode scan, formula scan, and the Python comparison |
| Terminal value formula missing its `(1+g)` | The Python comparison alone — it looks right |
| A balance sheet line dropped from the total | Balance identity, and the CHECKS tab |
| Interest charged on closing instead of opening balances | Circular reference, then the year-by-year comparison |
| Net debt not deducted in the IPO EV/EBITDA method | The Python comparison alone — the workbook was otherwise clean |

The last one is the argument for the whole design: it produced a
well-formed workbook with no error values and almost every internal check
passing. Only the independent recomputation caught it.

## Gate 2 — citation integrity

`scripts/audit_report.py` catches:

- a figure in a sentence with no filing, date or URL beside it
- a table row of numbers with no source column
- a hedge word ("roughly", "we estimate", "likely") not marked `INFERENCE`
- recommendation language, by pattern — "undervalued", "attractive entry",
  "price target", "should buy", "bullish on"
- missing required sections for the report type

The advice patterns are deliberately aggressive. Describing someone else's
stance is legitimate; the fix is to attribute it ("Morgan Stanley's note of
2026-09-02 describes..."), which clears the check and improves the sentence.

## Gate 3 — adversarial read

Automated checks cannot catch a figure that is correctly cited to the wrong
line of the right document, or a conclusion that does not follow from the
evidence under it. So a fresh agent that has not seen the work being
produced gets the deliverables and this brief:

> You are auditing a finance report you did not write. Assume it contains at
> least one error, because it probably does.
>
> 1. Pick three figures at random, open their cited sources, and confirm the
>    figure appears there and says what the report claims it says. Report
>    exactly what you found, including when it checked out.
> 2. Recompute the valuation bridge by hand from the stated inputs:
>    PV of explicit FCF + PV of terminal value - net debt, over share count.
>    Does it reconcile to the stated value per share?
> 3. Find every sentence that tells the reader what to do, or implies it.
>    Quote each one.
> 4. Name the single weakest claim in the report and say why.
>
> Report findings only. Do not fix anything, and do not express a view on
> the company.

Its findings are acted on before delivery. Anything unresolved is disclosed
in the delivery message rather than quietly dropped.

## Gate 4 — the confidence statement

Every delivery ends with what was actually checked:

```
Verification: model audit PASS (14/14) · citation audit PASS ·
adversarial review PASS with 1 note (see below). 23 of 25 figures traced to
primary filings; 2 marked COULD NOT VERIFY in §4.
```

If a gate was skipped, say which and why. If a gate failed and was fixed,
the statement reports the final state. Never report a gate that did not run.

## When a gate fails

Fix and re-run. Do not explain a failure away in prose, do not relax a
threshold to make it pass, and do not deliver with a note saying the audit
failed but the file is probably fine. The only legitimate exception is the
`REVIEW` state on the exit-multiple cross-check, which flags a wide gap
between the two terminal-value methods — that is a finding to explain in the
memo, not an error to suppress.
