# Module M — Model Builder

Produces a working `.xlsx` — a model, not a picture of one. The test: change
one cell on INPUTS and every downstream number moves.

Report and analyse only. The model outputs a value, a return or a price under
stated assumptions; it does not output a verdict.

## Pick the model type

| The user wants | `--type` | What it answers |
|---|---|---|
| A valuation, a DCF, "what is it worth" | `dcf` | Intrinsic value per share, against the market price |
| "Break down the company's finances", a full operating model, a forecast of the accounts | `statements` | How the three statements move together, where cash comes from and goes |
| A buyout, sponsor returns, "could PE take this out" | `lbo` | IRR and money multiple, and where the return actually comes from |
| A listing, "what would it price at", a float | `ipo` | Offer price, proceeds, dilution, how it prices against peers |

Several can apply. A full workup on a private-equity target is `statements`
then `lbo`; a pre-IPO company is `statements` then `ipo`. Build them in that
order, because the statements model is where the operating case gets tested.

If the user does not say, infer from the question and say which you chose in
one line. Do not stop to ask.

## The history requirement

**Seven to twelve years, not three.** The builder refuses fewer than seven.
This is not pedantry: a five-year window on a company that last had a bad
year six years ago will show you a business that has never had one. Ten years
usually spans a downturn, and the trough is what the forecast has to survive.

Every model type's HISTORICALS tab carries a statistics block — CAGR, margin
range, worst year, how many years revenue fell — and the forecast is checked
against it:

```bash
python3 scripts/build_model.py SPEC.json --history
```

This prints the range each driver has actually occupied and flags any forecast
assumption sitting outside it. An assumption above the ten-year high is not
forbidden; it needs a stated reason, in the memo, in a sentence.

## The build is script-driven, not hand-assembled

Do **not** write cells one at a time in an ad-hoc script. The workbook is
generated from a JSON spec so that the same spec can be audited independently:

```bash
python3 scripts/build_model.py SPEC.json --type <type> -o TICK-<type>.xlsx
python3 scripts/audit_model.py TICK-<type>.xlsx --spec SPEC.json --type <type>
```

Your job is to produce a correct, fully sourced spec. The scripts guarantee
the structural rules and the audit proves them. Start from the matching file
in `templates/`:

| Type | Template |
|---|---|
| `dcf` | `templates/spec-dcf.json` |
| `statements` | `templates/spec-statements.json` |
| `lbo` | `templates/spec-lbo.json` |
| `ipo` | `templates/spec-ipo.json` |

Every historical figure needs a `source` naming the filing and its date. Every
input needs a `basis` saying where the assumption came from — a historical
average, company guidance, or your own estimate (then say `estimate` and list
the key under `estimates`, which renders it amber in the workbook). The
builder refuses to run without both. That refusal is the feature.

## Type-specific notes

### `dcf`

**Derive, don't assert.** A spec with a `wacc_build` section produces a WACC
tab that shows the whole working, and INPUTS then *links* to it so one number
has one home:

- **Beta** from a peer set, each peer's observed beta unlevered (Hamada) to
  strip out its financing, the median re-levered at the target structure —
  and, separately, a regression beta shrunk toward 1.0 (Blume), because betas
  drift. `beta_source` picks comps, regression, or the average of the two.
  Record the regression's R²: a low one is a reason to lean on the peers.
- **Equity risk premium** from a market return history (10 years minimum,
  longer is better) plus the dividend yield, less the risk-free rate — not a
  round number pulled from a textbook.
- **Cost of debt** from interest actually paid over gross debt, which is what
  the company borrows at, rather than what a rating table says it should.
- **Capital structure** at a target, not today's accident of market prices.

A terminal growth rate above long-run nominal GDP for the company's market is
a modelling error unless argued.

**Beta from the regression, not from a number.** Supply `prices` (two
aligned close series, stock and index, 30 observations minimum) under
`regression_beta` and the BETA_REGRESSION tab computes the returns, the slope,
the intercept and R² in the sheet, with the WACC tab linking to the slope.
Report the R²: a beta from a regression explaining a third of the share's
movement deserves less weight than one from a tight fit, and `beta_source`
is how you act on that. An asserted `raw_beta` is still accepted when no
series is available — it is just weaker.

**The top line, built up.** Supply `segments` (each with a historical revenue
series, a forecast growth path, a basis and a source) and the SEGMENTS tab
drives revenue from the parts. The group growth rate on INPUTS then becomes a
*formula* linking to the segment build rather than an assumption: a mix shift
toward a faster-growing segment lifts group growth without anyone asserting
that it does, and a decelerating group rate falls out of the arithmetic
instead of being typed in. Historical segments must sum to reported revenue
in every year — the validator refuses the build otherwise, because the usual
cause is a missing segment or an unnoticed restatement.

**Intrinsic growth.** The INTRINSIC_GROWTH tab computes g = reinvestment rate
× ROIC from the reported accounts: what the business can fund out of what it
earns and ploughs back. It is not a forecast — it is the benchmark the
forecast is judged against. Projecting growth above it is allowed and often
right, but the memo must say what pays for it: margin expansion, better
capital efficiency, or acquisition. The audit reports the gap; it does not
fail the model for it.

**Valuation date, not year end.** `first_period_fraction` sets how far the
first cash flow sits from today — 1.00 for year-end discounting, 0.50 for the
mid-year convention, or a stub like 0.45 when nearly half the fiscal year has
already gone. Getting this wrong is worth several percent of value and is
invisible in the output.

**Cross-checks that earn their place.** RELATIVE_PRICING carries the full
peer distribution (high, 75th, median, average, 25th, low) across EV/Revenue,
EV/EBITDA and P/E, with the implied value per share at each quartile — a lone
median hides the spread, and the spread is the honest part. SCENARIOS re-runs
the whole model at bear/base/bull growth. FOOTBALL_FIELD puts every method's
range on one scale, which is the right way to show a valuation: where the
bands overlap, not a single false-precision number.

Choose the sensitivity axes from evidence, not habit:

```bash
python3 scripts/build_model.py SPEC.json --scan        # rank drivers by impact
python3 scripts/build_model.py SPEC.json --breakeven wacc,ebit_margin
```

`--scan` perturbs each input ±10% and ranks by effect on value per share.
`--breakeven` solves what each would have to do to move the answer 30%. Use
the top two unless both are discounting assumptions, in which case take the
highest-ranked operating driver with `--x-axis`. State which two you picked
and why, citing the scan.

### `statements`
Needs a full reported balance sheet, income statement **and** operating cash
flow — including historical net income, interest expense and CFO, which the
DUPONT and RATIOS tabs are built from.

The DUPONT tab splits return on equity into margin, asset turnover and
leverage, on **average** balances. Averages matter: a company that raised
equity in December has a closing balance that financed none of the year's
profit. Two companies with the same ROE can be entirely different businesses
and this is what says which.

RATIOS runs history and forecast on one line so a break at the boundary is
visible: growth, margins, working capital days and the cash conversion cycle,
fixed asset turnover, leverage and interest cover, ROCE and ROE, retention and
sustainable growth (retention × ROE), and the cash-flow ratios — CFO over
revenue, over assets, over debt. A forecast whose ratios step sharply at the
first projected year is making a claim that needs a sentence. The spec
validator checks that **each reported year balances** — assets against
liabilities plus equity — and refuses the build if not, because that is nearly
always a transcription error rather than a rounding one.

Two conventions, both stated on the README tab: interest is charged on opening
balances (so there is no circular reference and no iterative calculation), and
a revolver is the cash plug, drawing to hold the minimum balance and sweeping
surplus cash to repay itself. Other assets and other liabilities are held flat
rather than forecast — say so rather than implying precision.

Working capital is driven by days (DSO, DIO, DPO), not percentages, so the
RATIOS tab can show the cash conversion cycle beside the history.

### `lbo`
Debt is sized in turns of LTM EBITDA and tranches are listed in priority
order; the sweep pays them down in that order. The value attribution is an
identity — EBITDA growth plus multiple change plus debt paydown equals exactly
the change in equity value — and the audit tests that the residual is zero.

Two things to say out loud in the memo: opening leverage, and how much of the
return comes from multiple expansion. A deal that needs a higher exit multiple
than entry is making an assumption about the market, not the business. The
default convention is exit at entry, and departing from it needs a reason.

### `ipo`
Priced off a weighted blend of three peer methods (EV/EBITDA, EV/Sales, P/E)
on NTM figures, with the weights as visible inputs, then an IPO discount. The
discount is the most judgemental number in the model and is one axis of the
sensitivity grid for exactly that reason.

The use-of-proceeds table must reconcile to net primary proceeds. If it does
not, report the unallocated balance — never invent a purpose to close it.

## The memo (outside the file)

Deliver alongside the workbook:

1. **The three assumptions it hangs on** — named, with their values and the
   scan rank that justifies calling them load-bearing.
2. **What each would have to be to move the answer 30%** — computed with
   `--breakeven`, not guessed.
3. **The three biggest risks, and whether the model captures them at all.**
   The honest answer is often no: a DCF cannot represent a regulatory ban, and
   an LBO cannot represent a covenant breach it was not told about. Say which
   risks live entirely outside the model.
4. **Where the forecast departs from the historical record**, from `--history`,
   with the reason for each departure.

## Before delivering

The audit must exit 0. Then look at the recalculated outputs yourself: an
implied multiple far outside the peer range, an IRR that depends mostly on
multiple expansion, a margin that never dips in a business whose history says
it does — these pass every mechanical check and are still worth a sentence in
the memo.
