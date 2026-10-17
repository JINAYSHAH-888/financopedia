"""
Independent LBO engine.

Sources and uses at entry, a tranched debt schedule with mandatory
amortisation and a cash sweep, exit at a multiple, and the classic three-way
attribution of value created.

Conventions worth knowing when reading the workbook:

* Debt is sized in turns of LTM EBITDA, so the capital structure does not
  move when the entry multiple does. That is what makes the sensitivity grid
  a closed form rather than a full re-run.
* Interest is charged on opening balances -- no circularity, no iteration.
* The sweep pays tranches down in the order they are listed, which is the
  order of priority.
* The attribution is an identity, not an approximation: EBITDA growth plus
  multiple change plus debt paydown equals exactly the change in equity
  value. The CHECKS tab tests that it does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import dcf_core as core
from dcf_core import SpecError, irr

REQUIRED_HIST = ["years", "revenue", "ebitda", "capex", "nwc_balance"]

SCALARS = ["entry_multiple", "exit_multiple", "transaction_fees_pct",
           "financing_fees_pct", "rollover_equity", "tax_rate",
           "cash_sweep_pct", "min_cash", "opening_cash", "interest_rate_cash",
           "entry_step", "exit_step"]

VECTORS = ["rev_growth", "ebitda_margin", "da_pct_rev", "capex_pct_rev",
           "nwc_pct_rev"]

PRESENTATION = {"entry_step", "exit_step"}


def validate(spec: Dict[str, Any]) -> None:
    problems: List[str] = []
    core.validate_common(spec, problems)
    core.validate_hist_vectors(spec, REQUIRED_HIST, problems)
    core.validate_inputs(spec, SCALARS, VECTORS, problems, PRESENTATION)

    tranches = spec.get("debt_tranches", [])
    if not tranches:
        problems.append("debt_tranches is required -- an LBO with no debt is "
                        "not an LBO")
    for k, tr in enumerate(tranches):
        for key in ("name", "turns", "rate", "amort_pct"):
            if key not in tr:
                problems.append(f"debt_tranches[{k}].{key} is required")
        if not tr.get("basis"):
            problems.append(f"debt_tranches[{k}].basis is required -- say where "
                            "the sizing and pricing came from")
    if problems:
        raise SpecError("spec validation failed:\n  - " + "\n  - ".join(problems))


@dataclass
class Lbo:
    ltm_ebitda: float = 0.0
    entry_ev: float = 0.0
    tranche_amounts: List[float] = field(default_factory=list)
    total_debt: float = 0.0
    transaction_fees: float = 0.0
    financing_fees: float = 0.0
    cash_to_bs: float = 0.0
    total_uses: float = 0.0
    rollover: float = 0.0
    sponsor_equity: float = 0.0
    total_sources: float = 0.0
    entry_net_debt: float = 0.0
    entry_equity_value: float = 0.0
    entry_leverage: float = 0.0

    years: List[int] = field(default_factory=list)
    revenue: List[float] = field(default_factory=list)
    ebitda: List[float] = field(default_factory=list)
    da: List[float] = field(default_factory=list)
    ebit: List[float] = field(default_factory=list)
    interest: List[float] = field(default_factory=list)
    interest_income: List[float] = field(default_factory=list)
    pbt: List[float] = field(default_factory=list)
    tax: List[float] = field(default_factory=list)
    net_income: List[float] = field(default_factory=list)
    capex: List[float] = field(default_factory=list)
    nwc: List[float] = field(default_factory=list)
    delta_nwc: List[float] = field(default_factory=list)
    fcf: List[float] = field(default_factory=list)

    opening_balances: List[List[float]] = field(default_factory=list)
    mandatory: List[List[float]] = field(default_factory=list)
    sweep: List[List[float]] = field(default_factory=list)
    closing_balances: List[List[float]] = field(default_factory=list)
    total_closing_debt: List[float] = field(default_factory=list)
    opening_cash: List[float] = field(default_factory=list)
    closing_cash: List[float] = field(default_factory=list)
    cash_available: List[float] = field(default_factory=list)
    net_debt: List[float] = field(default_factory=list)
    leverage: List[float] = field(default_factory=list)

    exit_ebitda: float = 0.0
    exit_ev: float = 0.0
    exit_net_debt: float = 0.0
    exit_equity: float = 0.0
    money_multiple: float = 0.0
    irr: float = 0.0
    attr_ebitda_growth: float = 0.0
    attr_multiple: float = 0.0
    attr_debt_paydown: float = 0.0
    attr_total: float = 0.0


def run(spec: Dict[str, Any]) -> Lbo:
    i, h = spec["inputs"], spec["historicals"]
    tr = spec["debt_tranches"]
    nf, nt = core.n_fcst(spec), len(tr)
    m = Lbo(years=core.fcst_years(spec))

    # ---- entry ---------------------------------------------------------
    m.ltm_ebitda = h["ebitda"][-1]
    m.entry_ev = i["entry_multiple"] * m.ltm_ebitda
    m.tranche_amounts = [t["turns"] * m.ltm_ebitda for t in tr]
    m.total_debt = sum(m.tranche_amounts)
    m.transaction_fees = m.entry_ev * i["transaction_fees_pct"]
    m.financing_fees = m.total_debt * i["financing_fees_pct"]
    m.cash_to_bs = i["opening_cash"]
    m.total_uses = (m.entry_ev + m.transaction_fees + m.financing_fees
                    + m.cash_to_bs)
    m.rollover = i["rollover_equity"]
    m.sponsor_equity = m.total_uses - m.total_debt - m.rollover
    m.total_sources = m.total_debt + m.rollover + m.sponsor_equity
    m.entry_net_debt = m.total_debt - i["opening_cash"]
    m.entry_equity_value = m.entry_ev - m.entry_net_debt
    m.entry_leverage = m.entry_net_debt / m.ltm_ebitda if m.ltm_ebitda else float("nan")

    # ---- operating forecast and debt schedule --------------------------
    balances = list(m.tranche_amounts)
    cash = i["opening_cash"]
    prev_rev = h["revenue"][-1]
    prev_nwc = h["nwc_balance"][-1]

    for t in range(nf):
        rev = prev_rev * (1 + i["rev_growth"][t])
        ebitda = rev * i["ebitda_margin"][t]
        da = rev * i["da_pct_rev"][t]
        ebit = ebitda - da
        capex = rev * i["capex_pct_rev"][t]
        nwc = rev * i["nwc_pct_rev"][t]
        dnwc = nwc - prev_nwc

        opening = list(balances)
        interest = sum(opening[k] * tr[k]["rate"] for k in range(nt))
        int_income = cash * i["interest_rate_cash"]
        pbt = ebit - interest + int_income
        tax = max(pbt, 0.0) * i["tax_rate"]
        ni = pbt - tax
        fcf = ni + da - capex - dnwc

        mand = [min(tr[k]["amort_pct"] * m.tranche_amounts[k], opening[k])
                for k in range(nt)]
        total_mand = sum(mand)
        cash_before = cash + fcf - total_mand
        available = max(0.0, cash_before - i["min_cash"]) * i["cash_sweep_pct"]

        sweeps, remaining = [], available
        for k in range(nt):
            if not tr[k].get("sweep", True):
                sweeps.append(0.0)
                continue
            s = min(opening[k] - mand[k], max(0.0, remaining))
            sweeps.append(s)
            remaining -= s
        total_sweep = sum(sweeps)
        cash = cash_before - total_sweep
        balances = [opening[k] - mand[k] - sweeps[k] for k in range(nt)]

        m.revenue.append(rev); m.ebitda.append(ebitda); m.da.append(da)
        m.ebit.append(ebit); m.interest.append(interest)
        m.interest_income.append(int_income); m.pbt.append(pbt); m.tax.append(tax)
        m.net_income.append(ni); m.capex.append(capex); m.nwc.append(nwc)
        m.delta_nwc.append(dnwc); m.fcf.append(fcf)
        m.opening_balances.append(opening); m.mandatory.append(mand)
        m.sweep.append(sweeps); m.closing_balances.append(list(balances))
        m.total_closing_debt.append(sum(balances))
        m.opening_cash.append(cash_before - fcf + total_mand)
        m.closing_cash.append(cash)
        m.cash_available.append(available)
        m.net_debt.append(sum(balances) - cash)
        m.leverage.append((sum(balances) - cash) / ebitda if ebitda else float("nan"))

        prev_rev, prev_nwc = rev, nwc

    # ---- exit ----------------------------------------------------------
    m.exit_ebitda = m.ebitda[-1]
    m.exit_ev = i["exit_multiple"] * m.exit_ebitda
    m.exit_net_debt = m.net_debt[-1]
    m.exit_equity = m.exit_ev - m.exit_net_debt
    m.money_multiple = (m.exit_equity / m.sponsor_equity
                        if m.sponsor_equity else float("nan"))
    m.irr = irr([-m.sponsor_equity] + [0.0] * (nf - 1) + [m.exit_equity])

    m.attr_ebitda_growth = (m.exit_ebitda - m.ltm_ebitda) * i["entry_multiple"]
    m.attr_multiple = (i["exit_multiple"] - i["entry_multiple"]) * m.exit_ebitda
    m.attr_debt_paydown = m.entry_net_debt - m.exit_net_debt
    m.attr_total = (m.attr_ebitda_growth + m.attr_multiple + m.attr_debt_paydown)
    return m


def sponsor_equity_at(spec: Dict[str, Any], entry_multiple: float,
                      m: Lbo) -> float:
    i = spec["inputs"]
    ev = entry_multiple * m.ltm_ebitda
    uses = (ev + ev * i["transaction_fees_pct"] + m.financing_fees
            + i["opening_cash"])
    return uses - m.total_debt - i["rollover_equity"]


def irr_at(spec: Dict[str, Any], entry_multiple: float, exit_multiple: float,
           m: Lbo) -> float:
    """IRR for a grid cell.

    Debt is sized in turns of EBITDA, so neither the debt schedule nor the
    cash flows depend on the entry or exit multiple; only the sponsor cheque
    and the exit equity do. That makes the grid exact rather than approximate.
    """
    sponsor = sponsor_equity_at(spec, entry_multiple, m)
    exit_eq = exit_multiple * m.exit_ebitda - m.exit_net_debt
    if sponsor <= 0 or exit_eq <= 0:
        return float("nan")
    return (exit_eq / sponsor) ** (1 / core.n_fcst(spec)) - 1
