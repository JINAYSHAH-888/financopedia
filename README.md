# Financopedia

A finance agent packaged as a Claude skill: research, four kinds of Excel
model, and earnings-call review — each gated by an automated audit that
recalculates the workbook and checks it against an independently written
Python engine.

Research and analysis only. It never tells you what to buy or sell, and
nothing it produces is financial advice.

```
research NVDA
build me a DCF for Maruti Suzuki
break down HDFC Bank's financials
could a sponsor LBO this? what's the IRR?
what would Newco price at if it listed?
```

## Quick start

As a Claude skill — zip the folder and upload it in
**Settings → Capabilities → Skills**, then just ask in plain language.

As a standalone toolkit:

```bash
pip install -r requirements.txt
sudo apt-get install libreoffice-calc        # needed by the audit

python3 scripts/build_model.py templates/spec-dcf.json --type dcf -o model.xlsx
python3 scripts/audit_model.py model.xlsx --spec templates/spec-dcf.json --type dcf
```

Build everything and audit it in one go:

```bash
bash tests/run_all.sh
```

Sample output for each model type is in `examples/`. Every figure in it is
invented — they are structure demonstrations, not analysis.

## The four models

| Type | Tabs | Answers |
|---|---|---|
| `dcf` | INPUTS · HISTORICALS · **SEGMENTS** · **BETA_REGRESSION** · **WACC** · PROJECTION · VALUATION · **INTRINSIC_GROWTH** · **RELATIVE_PRICING** · SENSITIVITY · **SCENARIOS** · **FOOTBALL_FIELD** · CHECKS | What it's worth, against the market price |
| `statements` | + INCOME · BALANCE · CASHFLOW · RATIOS · **DUPONT** | How the whole company's finances move together |
| `lbo` | + SOURCES_USES · DEBT · RETURNS | Sponsor IRR, and where the return actually comes from |
| `ipo` | + VALUATION · OFFERING · PROCEEDS | Offer price, dilution, proceeds, pricing vs peers |

### Derived, not asserted

The difference between a model and a spreadsheet of opinions is whether the
inputs can be checked. So the DCF derives what most models assert:

- **Beta** — regressed from a price series in the sheet (slope, alpha, R²),
  and separately from peers unlevered (Hamada) and re-levered at a target
  structure. `beta_source` picks one or blends them.
- **The top line** — built from segments, each on its own growth path, so the
  group growth rate is a consequence of the mix rather than an assumption.
  Historical segments must sum to reported revenue.
- **Equity risk premium** — from a market return history plus dividend yield,
  less the risk-free rate.
- **Cost of debt** — interest actually paid over gross debt.
- **Growth** — `INTRINSIC_GROWTH` computes reinvestment rate × ROIC from the
  accounts. Forecasting above it is allowed; the memo has to say what pays
  for it.
- **The answer itself** — `FOOTBALL_FIELD` shows every method's range on one
  scale rather than a single false-precision number, and `SCENARIOS` re-runs
  the whole model bear/base/bull.

`first_period_fraction` discounts from the valuation date rather than the
fiscal year end (1.00 year-end, 0.50 mid-year, or a stub).

All four demand **7 to 12 years of history** and refuse to build on less. A
five-year window on a company that last had a bad year six years ago shows
you a business that has never had one. Ten years usually spans a downturn,
and the trough is what a forecast has to survive — so every model carries a
statistics block (CAGR, margin range, worst year, how many years revenue
fell) and checks the forecast against it.

```bash
python3 scripts/build_model.py SPEC.json --history
```

prints that range and flags any assumption sitting outside it.

## The verification layer

This is what makes the output trustworthy without you checking it.

**`audit_model.py`** recalculates the workbook headlessly through
LibreOffice and compares every output against an independent engine written
separately in Python. It also proves there are no hardcoded numbers outside
INPUTS, every historical figure carries a filing, and every assumption
states its basis. Then each type's own identity: the balance sheet balances
every year, sources equal uses, the LBO value attribution is exact to the
cent, post-money value per share equals the offer price. Exit 0 or the file
does not ship.

**Tested by sabotage**, because checks that never fail prove nothing. A
hardcoded projection cell, a terminal-value formula missing its `(1+g)`, a
balance-sheet line dropped from the total, interest charged on closing
instead of opening balances, and a missing net-debt deduction in the IPO
valuation were all caught. The last two are the argument for the design:
the IPO sabotage produced a clean, well-formed workbook with no error values
and almost every internal check passing — only the independent
recomputation found it.

**`audit_report.py`** flags any figure without a source and date, any
estimate not marked `INFERENCE`, and any recommendation language — the drift
from analysis into advice that these tools fall into by default.

**Adversarial read.** A fresh agent that never saw the work tries to break
it: tracing figures to sources, recomputing the bridge by hand, hunting for
advice drift.

**Honest confidence.** Every delivery ends with what was actually checked.
The gates prove internal consistency and provenance — if the sources are
right, the output is right, and you can see every source. They cannot prove
a filing was honest or a projection will hold, and the skill is instructed
never to claim otherwise.

## Using the scripts directly

```bash
python3 scripts/build_model.py SPEC.json --type dcf        -o TICK-dcf.xlsx
python3 scripts/build_model.py SPEC.json --type statements -o TICK-statements.xlsx
python3 scripts/build_model.py SPEC.json --type lbo        -o TICK-lbo.xlsx
python3 scripts/build_model.py SPEC.json --type ipo        -o TICK-ipo.xlsx

python3 scripts/build_model.py SPEC.json --history               # the record
python3 scripts/build_model.py SPEC.json --scan                  # rank drivers
python3 scripts/build_model.py SPEC.json --breakeven wacc,ebit_margin
python3 scripts/audit_model.py TICK-dcf.xlsx --spec SPEC.json --type dcf
python3 scripts/audit_report.py research-TICK.md
```

Start from the matching file in `templates/`. The builder refuses to run on
a spec where a historical figure has no source or an assumption has no
basis, and the `statements` validator refuses a reported balance sheet that
doesn't balance — that refusal catches transcription errors before they
reach the model.

Requires `openpyxl` and LibreOffice (for the recalculation check).

## Files

```
SKILL.md                          routing, evidence rules, the four gates
references/research-protocol.md
references/model-protocol.md      choosing a type, the history rule, per-type notes
references/earnings-protocol.md
references/verification.md        what each gate proves, and the sabotage results
scripts/dcf_core.py               DCF engine, history stats, driver scan, IRR
scripts/valuation_core.py         WACC build-up, intrinsic growth, relative
                                  pricing, scenarios
scripts/build_dcf_extras.py       WACC / intrinsic / relative / scenarios /
                                  football field tabs
scripts/stmt_core.py              three-statement engine
scripts/lbo_core.py               LBO engine
scripts/ipo_core.py               IPO engine
scripts/build_model.py            dispatcher + DCF workbook
scripts/build_statements.py       three-statement workbook
scripts/build_lbo.py              LBO workbook
scripts/build_ipo.py              IPO workbook
scripts/audit_model.py            type-aware audit gate
scripts/audit_types.py            statements / LBO / IPO auditors
scripts/audit_lib.py              recalculation and comparison machinery
scripts/audit_report.py           citation and no-advice gate
scripts/xl_style.py               shared formatting and the colour key
templates/spec-dcf.json           worked examples — all figures invented,
templates/spec-statements.json    replace them and their sources
templates/spec-lbo.json
templates/spec-ipo.json
templates/notes-template.md
```


## Repository layout

```
SKILL.md                  routing, evidence rules, the four gates
references/               protocols: research, modelling, earnings, verification
scripts/                  engines, builders and auditors
templates/                worked example specs, one per model type
examples/                 sample output workbooks
tests/run_all.sh          build + audit every type
tests/test_sabotage.py    proves the gates still catch deliberate errors
.github/workflows/        CI: installs LibreOffice and runs both of the above
```

## Tests

`tests/run_all.sh` builds all four model types from their template specs and
runs the full audit on each.

`tests/test_sabotage.py` is the one that matters. Checks that never fail prove
nothing, so it breaks each model in a way that still produces a plausible
workbook — a hardcoded projection cell, a terminal value missing its `(1+g)`,
a beta re-levered without the tax shield, an index regressed on the stock, a
line dropped from the balance sheet total, interest on closing balances, a
missing net-debt deduction — and asserts the audit catches every one. CI runs
both on each push.

## What this cannot do

The gates prove internal consistency and provenance: the workbook computes
what it claims, every figure traces to a filing, nothing drifts into advice.
They cannot prove a filing was honest, a projection will hold, or that a
material fact was simply absent from every source searched. The beta
regression will happily produce a confident slope from a stale index or an
unadjusted price series. Sourcing is a human job; this checks the arithmetic
and the paper trail.

## Licence

MIT — see [LICENSE](LICENSE).
