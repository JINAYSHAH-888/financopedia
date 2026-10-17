"""
Independent three-statement engine: income statement, balance sheet and cash
flow statement, fully linked.

Design notes that matter when reading the workbook:

* Interest is charged on OPENING balances, not average balances. That removes
  the circular reference that otherwise forces iterative calculation, at the
  cost of slightly understating interest in a year of heavy drawdown. It is a
  deliberate trade and it is stated on the README tab.
* A revolver is the cash plug: it draws whatever keeps cash at the minimum,
  and sweeps surplus cash above the minimum to repay itself.
* Other assets, other current liabilities and other long-term liabilities are
  held flat from the last reported balance sheet. They are not forecast, and
  the workbook says so rather than implying precision it does not have.

The balance sheet balances by construction, which is exactly why the CHECKS
tab tests it: if it ever stops balancing, something upstream is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import dcf_core as core
from dcf_core import SpecError

HIST_IS = ["revenue", "cogs", "sga", "da", "capex", "net_income",
           "interest_expense", "cfo"]
HIST_ASSETS = ["cash", "ar", "inventory", "other_ca", "ppe_net", "other_assets"]
HIST_LIABS = ["ap", "accrued", "other_cl", "debt", "other_lt_liab", "equity"]
REQUIRED_HIST = ["years"] + HIST_IS + HIST_ASSETS + HIST_LIABS

SCALARS = ["tax_rate", "interest_rate_debt", "interest_rate_revolver",
           "interest_rate_cash", "min_cash", "dividend_payout",
           "opening_revolver"]

VECTORS = ["rev_growth", "gross_margin", "sga_pct_rev", "da_pct_rev",
           "capex_pct_rev", "dso", "dio", "dpo", "other_ca_pct_rev",
           "accrued_pct_rev", "debt_repayment"]

DAYS = 365.0


def total_assets_hist(spec, t):
    h = spec["historicals"]
    return sum(h[k][t] for k in HIST_ASSETS)


def total_liabs_hist(spec, t):
    h = spec["historicals"]
    return sum(h[k][t] for k in HIST_LIABS)


def validate(spec: Dict[str, Any]) -> None:
    problems: List[str] = []
    core.validate_common(spec, problems)
    core.validate_hist_vectors(spec, REQUIRED_HIST, problems)
    core.validate_inputs(spec, SCALARS, VECTORS, problems)
    if problems:
        raise SpecError("spec validation failed:\n  - " + "\n  - ".join(problems))

    # the transcription check: a reported balance sheet must balance
    off = []
    for t in range(core.n_hist(spec)):
        a, le = total_assets_hist(spec, t), total_liabs_hist(spec, t)
        if abs(a - le) / max(abs(a), 1.0) > 1e-4:
            off.append(f"{spec['historicals']['years'][t]}: assets {a:,.1f} vs "
                       f"liabilities+equity {le:,.1f} (off by {a - le:,.1f})")
    if off:
        raise SpecError(
            "historical balance sheet does not balance -- this is almost always "
            "a transcription error, not a rounding one:\n  - " + "\n  - ".join(off))


@dataclass
class Statements:
    years: List[int] = field(default_factory=list)
    # income statement
    revenue: List[float] = field(default_factory=list)
    cogs: List[float] = field(default_factory=list)
    gross_profit: List[float] = field(default_factory=list)
    sga: List[float] = field(default_factory=list)
    ebitda: List[float] = field(default_factory=list)
    da: List[float] = field(default_factory=list)
    ebit: List[float] = field(default_factory=list)
    interest_expense: List[float] = field(default_factory=list)
    interest_income: List[float] = field(default_factory=list)
    pbt: List[float] = field(default_factory=list)
    tax: List[float] = field(default_factory=list)
    net_income: List[float] = field(default_factory=list)
    dividends: List[float] = field(default_factory=list)
    # balance sheet
    cash: List[float] = field(default_factory=list)
    ar: List[float] = field(default_factory=list)
    inventory: List[float] = field(default_factory=list)
    other_ca: List[float] = field(default_factory=list)
    ppe_net: List[float] = field(default_factory=list)
    total_assets: List[float] = field(default_factory=list)
    ap: List[float] = field(default_factory=list)
    accrued: List[float] = field(default_factory=list)
    debt: List[float] = field(default_factory=list)
    revolver: List[float] = field(default_factory=list)
    equity: List[float] = field(default_factory=list)
    total_liabs_equity: List[float] = field(default_factory=list)
    balance_diff: List[float] = field(default_factory=list)
    nwc: List[float] = field(default_factory=list)
    # cash flow
    delta_nwc: List[float] = field(default_factory=list)
    cfo: List[float] = field(default_factory=list)
    capex: List[float] = field(default_factory=list)
    cfi: List[float] = field(default_factory=list)
    debt_repayment: List[float] = field(default_factory=list)
    revolver_draw: List[float] = field(default_factory=list)
    revolver_repay: List[float] = field(default_factory=list)
    cff: List[float] = field(default_factory=list)
    net_change_cash: List[float] = field(default_factory=list)
    opening_cash: List[float] = field(default_factory=list)
    unlevered_fcf: List[float] = field(default_factory=list)
    levered_fcf: List[float] = field(default_factory=list)
    net_debt: List[float] = field(default_factory=list)


def run(spec: Dict[str, Any]) -> Statements:
    i, h = spec["inputs"], spec["historicals"]
    nf = core.n_fcst(spec)
    s = Statements(years=core.fcst_years(spec))

    prev_rev = h["revenue"][-1]
    cash = h["cash"][-1]
    ppe = h["ppe_net"][-1]
    debt = h["debt"][-1]
    revolver = i["opening_revolver"]
    equity = h["equity"][-1]
    other_ca_h = h["other_ca"][-1]
    prev_nwc = (h["ar"][-1] + h["inventory"][-1] + other_ca_h
                - h["ap"][-1] - h["accrued"][-1])
    other_assets = h["other_assets"][-1]
    other_cl = h["other_cl"][-1]
    other_lt = h["other_lt_liab"][-1]

    for t in range(nf):
        rev = prev_rev * (1 + i["rev_growth"][t])
        cogs = rev * (1 - i["gross_margin"][t])
        gross = rev - cogs
        sga = rev * i["sga_pct_rev"][t]
        ebitda = gross - sga
        da = rev * i["da_pct_rev"][t]
        ebit = ebitda - da
        capex = rev * i["capex_pct_rev"][t]

        # interest on opening balances -- no circularity
        int_exp = debt * i["interest_rate_debt"] + revolver * i["interest_rate_revolver"]
        int_inc = cash * i["interest_rate_cash"]
        pbt = ebit - int_exp + int_inc
        tax = max(pbt, 0.0) * i["tax_rate"]
        ni = pbt - tax
        div = max(ni, 0.0) * i["dividend_payout"]

        ar = rev / DAYS * i["dso"][t]
        inv = cogs / DAYS * i["dio"][t]
        ap = cogs / DAYS * i["dpo"][t]
        oca = rev * i["other_ca_pct_rev"][t]
        acc = rev * i["accrued_pct_rev"][t]
        nwc = ar + inv + oca - ap - acc
        dnwc = nwc - prev_nwc

        cfo = ni + da - dnwc
        cfi = -capex
        repay = min(i["debt_repayment"][t], debt)
        opening_cash = cash

        cash_before = opening_cash + cfo + cfi - repay - div
        draw = max(0.0, i["min_cash"] - cash_before)
        repay_rev = min(revolver, max(0.0, cash_before - i["min_cash"]))
        cff = -repay - div + draw - repay_rev
        net_change = cfo + cfi + cff
        cash = opening_cash + net_change

        ppe = ppe + capex - da
        debt = debt - repay
        revolver = revolver + draw - repay_rev
        equity = equity + ni - div

        assets = cash + ar + inv + oca + ppe + other_assets
        liabs_eq = ap + acc + other_cl + debt + revolver + other_lt + equity

        s.revenue.append(rev); s.cogs.append(cogs); s.gross_profit.append(gross)
        s.sga.append(sga); s.ebitda.append(ebitda); s.da.append(da)
        s.ebit.append(ebit); s.interest_expense.append(int_exp)
        s.interest_income.append(int_inc); s.pbt.append(pbt); s.tax.append(tax)
        s.net_income.append(ni); s.dividends.append(div)
        s.cash.append(cash); s.ar.append(ar); s.inventory.append(inv)
        s.other_ca.append(oca); s.ppe_net.append(ppe)
        s.total_assets.append(assets)
        s.ap.append(ap); s.accrued.append(acc); s.debt.append(debt)
        s.revolver.append(revolver); s.equity.append(equity)
        s.total_liabs_equity.append(liabs_eq)
        s.balance_diff.append(assets - liabs_eq)
        s.nwc.append(nwc); s.delta_nwc.append(dnwc)
        s.cfo.append(cfo); s.capex.append(capex); s.cfi.append(cfi)
        s.debt_repayment.append(repay); s.revolver_draw.append(draw)
        s.revolver_repay.append(repay_rev); s.cff.append(cff)
        s.net_change_cash.append(net_change); s.opening_cash.append(opening_cash)
        s.unlevered_fcf.append(ebit * (1 - i["tax_rate"]) + da - capex - dnwc)
        s.levered_fcf.append(cfo + cfi)
        s.net_debt.append(debt + revolver - cash)

        prev_rev, prev_nwc = rev, nwc

    return s


def dupont(spec: Dict[str, Any], s: Statements) -> Dict[str, List[float]]:
    """Three-step ROE and two-step ROA on AVERAGE balances.

    Averages matter: a company that issued equity in December has a closing
    balance that never financed any of the year's profit, and a closing-balance
    ROE flatters or punishes it for the timing alone.
    """
    h = spec["historicals"]
    n = len(s.revenue)
    open_assets = sum(h[k][-1] for k in HIST_ASSETS)
    open_equity = h["equity"][-1]

    out: Dict[str, List[float]] = {k: [] for k in
                                   ("net_margin", "asset_turnover",
                                    "equity_multiplier", "roe", "roe_direct",
                                    "roa", "avg_assets", "avg_equity")}
    for t in range(n):
        prev_assets = open_assets if t == 0 else s.total_assets[t - 1]
        prev_equity = open_equity if t == 0 else s.equity[t - 1]
        avg_a = (s.total_assets[t] + prev_assets) / 2
        avg_e = (s.equity[t] + prev_equity) / 2
        npm = s.net_income[t] / s.revenue[t]
        ato = s.revenue[t] / avg_a
        em = avg_a / avg_e
        out["avg_assets"].append(avg_a)
        out["avg_equity"].append(avg_e)
        out["net_margin"].append(npm)
        out["asset_turnover"].append(ato)
        out["equity_multiplier"].append(em)
        out["roe"].append(npm * ato * em)
        out["roe_direct"].append(s.net_income[t] / avg_e)
        out["roa"].append(npm * ato)
    return out


def ratios(spec: Dict[str, Any], s: Statements) -> Dict[str, List[float]]:
    """Forecast-period ratios -- the diagnostic read on the model."""
    out: Dict[str, List[float]] = {}
    n = len(s.revenue)
    prev_rev = spec["historicals"]["revenue"][-1]
    out["revenue_growth"] = []
    for t in range(n):
        base = prev_rev if t == 0 else s.revenue[t - 1]
        out["revenue_growth"].append(s.revenue[t] / base - 1)
    out["gross_margin"] = [s.gross_profit[t] / s.revenue[t] for t in range(n)]
    out["ebitda_margin"] = [s.ebitda[t] / s.revenue[t] for t in range(n)]
    out["ebit_margin"] = [s.ebit[t] / s.revenue[t] for t in range(n)]
    out["net_margin"] = [s.net_income[t] / s.revenue[t] for t in range(n)]
    out["ccc"] = [spec["inputs"]["dso"][t] + spec["inputs"]["dio"][t]
                  - spec["inputs"]["dpo"][t] for t in range(n)]
    out["net_debt_ebitda"] = [s.net_debt[t] / s.ebitda[t] if s.ebitda[t] else float("nan")
                              for t in range(n)]
    out["interest_cover"] = [s.ebit[t] / s.interest_expense[t]
                             if s.interest_expense[t] else float("nan")
                             for t in range(n)]
    # ROE on AVERAGE equity, consistent with the DuPont tab. Closing-balance
    # ROE flatters or punishes a company for the timing of an equity raise.
    out["roe"] = dupont(spec, s)["roe_direct"]
    out["fcf_conversion"] = [s.levered_fcf[t] / s.ebitda[t] if s.ebitda[t] else float("nan")
                             for t in range(n)]
    d = dupont(spec, s)
    out["roce"] = [s.ebit[t] / (s.total_assets[t] - (s.ap[t] + s.accrued[t]))
                   for t in range(n)]
    out["retention"] = [1 - (s.dividends[t] / s.net_income[t])
                        if s.net_income[t] else float("nan") for t in range(n)]
    out["sustainable_growth"] = [out["retention"][t] * d["roe_direct"][t]
                                 for t in range(n)]
    out["cfo_sales"] = [s.cfo[t] / s.revenue[t] for t in range(n)]
    out["cfo_assets"] = [s.cfo[t] / s.total_assets[t] for t in range(n)]
    out["cfo_debt"] = [s.cfo[t] / (s.debt[t] + s.revolver[t])
                       if (s.debt[t] + s.revolver[t]) else float("nan")
                       for t in range(n)]
    out["fixed_asset_turnover"] = [s.revenue[t] / s.ppe_net[t] if s.ppe_net[t]
                                   else float("nan") for t in range(n)]
    return out
