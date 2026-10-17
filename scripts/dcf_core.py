"""
Independent DCF engine for Financopedia.

Computes a valuation in pure Python from a spec dict. It knows nothing about
Excel. audit_model.py compares the recalculated workbook against this engine,
so the two implementations act as a check on each other -- a transcription
error in the workbook formulas shows up as a mismatch rather than as a
plausible wrong number.

Horizons are variable: 7 to 12 years of history, 3 to 10 forecast years.
Units follow the spec (typically millions of the reporting currency).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

MIN_HIST, MAX_HIST = 7, 12
MIN_FCST, MAX_FCST = 3, 10

REQUIRED_SCALARS = [
    "tax_rate", "risk_free", "equity_risk_premium", "beta", "cost_of_debt",
    "debt_weight", "terminal_growth", "exit_multiple", "net_debt",
    "shares_out", "current_price", "wacc_step", "g_step",
]

REQUIRED_VECTORS = [
    "rev_growth", "ebit_margin", "da_pct_rev", "capex_pct_rev", "nwc_pct_rev",
]

REQUIRED_HIST = ["years", "revenue", "ebit", "da", "capex", "nwc_balance"]

PRESENTATION_INPUTS = {"wacc_step", "g_step"}


class SpecError(ValueError):
    pass


# --------------------------------------------------------------------------
# horizon helpers -- every builder and auditor asks the spec, never a constant
# --------------------------------------------------------------------------


def n_hist(spec: Dict[str, Any]) -> int:
    return len(spec["historicals"]["years"])


def n_fcst(spec: Dict[str, Any]) -> int:
    return len(spec["inputs"]["rev_growth"])


def hist_years(spec: Dict[str, Any]) -> List[int]:
    return list(spec["historicals"]["years"])


def fcst_years(spec: Dict[str, Any]) -> List[int]:
    last = spec["historicals"]["years"][-1]
    return [last + k + 1 for k in range(n_fcst(spec))]


# --------------------------------------------------------------------------
# spec loading / validation
# --------------------------------------------------------------------------


def load_spec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    validate_spec(spec)
    return spec


def validate_common(spec: Dict[str, Any], problems: List[str]) -> None:
    """Meta and historical-horizon rules shared by every model type."""
    for section in ("meta", "historicals", "inputs"):
        if section not in spec:
            problems.append(f"missing top-level section: {section}")
    if problems:
        raise SpecError("; ".join(problems))

    for key in ("name", "ticker", "currency", "units", "as_of"):
        if not spec["meta"].get(key):
            problems.append(f"meta.{key} is required")

    years = spec["historicals"].get("years")
    if not years:
        problems.append("historicals.years is required")
        raise SpecError("; ".join(problems))
    nh = len(years)
    if not (MIN_HIST <= nh <= MAX_HIST):
        problems.append(
            f"historicals.years has {nh} entries; this skill requires "
            f"{MIN_HIST}-{MAX_HIST} years of history so the projection can be "
            "anchored to a real cycle, not three good years"
        )
    if sorted(years) != list(years):
        problems.append("historicals.years must run oldest to newest")


def validate_hist_vectors(spec, keys, problems, require_sources=True):
    nh = len(spec["historicals"].get("years", []))
    hist = spec["historicals"]
    for key in keys:
        if key == "years":
            continue
        if key not in hist:
            problems.append(f"historicals.{key} is required")
            continue
        if len(hist[key]) != nh:
            problems.append(
                f"historicals.{key} has {len(hist[key])} entries, expected {nh} "
                "(one per historical year)"
            )
    if require_sources:
        sources = hist.get("sources", {})
        for key in keys:
            if key == "years":
                continue
            if not sources.get(key):
                problems.append(
                    f"historicals.sources.{key} is required -- every figure needs a filing"
                )


def validate_inputs(spec, scalars, vectors, problems, presentation=frozenset()):
    inp = spec["inputs"]
    nf = None
    for key in vectors:
        if key not in inp:
            problems.append(f"inputs.{key} is required")
            continue
        if nf is None:
            nf = len(inp[key])
        elif len(inp[key]) != nf:
            problems.append(
                f"inputs.{key} has {len(inp[key])} entries but inputs.{vectors[0]} "
                f"has {nf}; all forecast drivers must share one horizon"
            )
    if nf is not None and not (MIN_FCST <= nf <= MAX_FCST):
        problems.append(f"forecast horizon is {nf} years; allowed range is "
                        f"{MIN_FCST}-{MAX_FCST}")
    for key in scalars:
        if key not in inp:
            problems.append(f"inputs.{key} is required")

    basis = inp.get("basis", {})
    for key in list(scalars) + list(vectors):
        if key in presentation:
            continue
        if not basis.get(key):
            problems.append(f"inputs.basis.{key} is required -- say where it came from")


BUILDUP_SUPPLIED = {"risk_free", "equity_risk_premium", "beta",
                    "cost_of_debt", "debt_weight"}


def validate_spec(spec: Dict[str, Any]) -> None:
    problems: List[str] = []
    validate_common(spec, problems)
    validate_hist_vectors(spec, REQUIRED_HIST, problems)
    scalars = list(REQUIRED_SCALARS)
    if spec.get("wacc_build"):
        # the build-up derives these, so asserting them too would be two
        # sources of truth for one number
        scalars = [k for k in scalars if k not in BUILDUP_SUPPLIED]
    validate_inputs(spec, scalars, REQUIRED_VECTORS, problems,
                    PRESENTATION_INPUTS)
    import valuation_core as vc
    vc.validate_wacc(spec, problems)
    vc.validate_regression(spec, problems)
    vc.validate_segments(spec, problems)
    if not problems:
        vc.apply_segments(spec)
    vc.validate_relative(spec, problems)
    if spec.get("wacc_build") or spec.get("intrinsic_growth", True):
        vc.validate_intrinsic(spec, problems)
    if problems:
        raise SpecError("spec validation failed:\n  - " + "\n  - ".join(problems))

    w = wacc(spec)
    if spec["inputs"]["terminal_growth"] >= w:
        raise SpecError(
            f"terminal_growth ({spec['inputs']['terminal_growth']:.3f}) >= WACC "
            f"({w:.3f}): the perpetuity formula diverges. Fix the assumption."
        )


# --------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------


def wacc(spec: Dict[str, Any]) -> float:
    """WACC from the build-up when the spec carries one, else from raw inputs.

    The build-up is the preferred path: it derives beta from a peer set and a
    regression, the equity risk premium from a market return history, and the
    cost of debt from interest actually paid. The raw-input path remains for
    specs that assert those numbers directly.
    """
    import valuation_core as vc
    if vc.has_buildup(spec):
        return vc.wacc_buildup(spec)["wacc"]
    i = spec["inputs"]
    cost_equity = i["risk_free"] + i["beta"] * i["equity_risk_premium"]
    wd = i["debt_weight"]
    return (1 - wd) * cost_equity + wd * i["cost_of_debt"] * (1 - i["tax_rate"])


def discount_periods(spec: Dict[str, Any]) -> List[float]:
    """Discount period for each forecast year.

    The first period may be a fraction of a year, so the valuation can be as
    of a date rather than a fiscal year end: 1.0 is year-end discounting, 0.5
    the mid-year convention, and a stub such as 0.42 the fraction of the
    current year still to come. Later periods add a full year each.
    """
    first = spec["inputs"].get("first_period_fraction", 1.0)
    return [first + t for t in range(n_fcst(spec))]


@dataclass
class Valuation:
    revenue: List[float] = field(default_factory=list)
    ebit: List[float] = field(default_factory=list)
    nopat: List[float] = field(default_factory=list)
    da: List[float] = field(default_factory=list)
    capex: List[float] = field(default_factory=list)
    nwc_balance: List[float] = field(default_factory=list)
    delta_nwc: List[float] = field(default_factory=list)
    fcf: List[float] = field(default_factory=list)
    discount_factors: List[float] = field(default_factory=list)
    pv_fcf: List[float] = field(default_factory=list)
    wacc: float = 0.0
    pv_explicit: float = 0.0
    terminal_value: float = 0.0
    pv_terminal: float = 0.0
    enterprise_value: float = 0.0
    equity_value: float = 0.0
    value_per_share: float = 0.0
    terminal_ebitda: float = 0.0
    tv_exit: float = 0.0
    ev_exit: float = 0.0
    value_per_share_exit: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def run(spec: Dict[str, Any]) -> Valuation:
    i, h = spec["inputs"], spec["historicals"]
    nf = n_fcst(spec)
    v = Valuation()
    v.wacc = wacc(spec)

    prev_rev = h["revenue"][-1]
    prev_nwc = h["nwc_balance"][-1]

    for t in range(nf):
        rev = prev_rev * (1 + i["rev_growth"][t])
        ebit = rev * i["ebit_margin"][t]
        nopat = ebit * (1 - i["tax_rate"])
        da = rev * i["da_pct_rev"][t]
        capex = rev * i["capex_pct_rev"][t]
        nwc = rev * i["nwc_pct_rev"][t]
        dnwc = nwc - prev_nwc

        v.revenue.append(rev)
        v.ebit.append(ebit)
        v.nopat.append(nopat)
        v.da.append(da)
        v.capex.append(capex)
        v.nwc_balance.append(nwc)
        v.delta_nwc.append(dnwc)
        v.fcf.append(nopat + da - capex - dnwc)

        prev_rev, prev_nwc = rev, nwc

    periods = discount_periods(spec)
    for t in range(nf):
        df = 1.0 / (1.0 + v.wacc) ** periods[t]
        v.discount_factors.append(df)
        v.pv_fcf.append(v.fcf[t] * df)

    v.pv_explicit = sum(v.pv_fcf)
    g = i["terminal_growth"]
    v.terminal_value = v.fcf[-1] * (1 + g) / (v.wacc - g)
    v.pv_terminal = v.terminal_value * v.discount_factors[-1]
    v.enterprise_value = v.pv_explicit + v.pv_terminal
    v.equity_value = v.enterprise_value - i["net_debt"]
    v.value_per_share = v.equity_value / i["shares_out"]

    v.terminal_ebitda = v.ebit[-1] + v.da[-1]
    v.tv_exit = v.terminal_ebitda * i["exit_multiple"]
    v.ev_exit = v.pv_explicit + v.tv_exit * v.discount_factors[-1]
    v.value_per_share_exit = (v.ev_exit - i["net_debt"]) / i["shares_out"]
    return v


# --------------------------------------------------------------------------
# historical analysis -- what 7-10 years of data is actually for
# --------------------------------------------------------------------------


def cagr(series: List[float], years: int) -> float:
    if series[0] <= 0 or series[-1] <= 0 or years <= 0:
        return float("nan")
    return (series[-1] / series[0]) ** (1 / years) - 1


def history_stats(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Range, average and trend over the full history.

    The reason for demanding 7-10 years: it lets the model state the
    historical range an assumption sits in, so a projected margin above
    anything the company has ever achieved is visible rather than implicit.
    """
    h = spec["historicals"]
    nh = n_hist(spec)
    rev, ebit = h["revenue"], h["ebit"]
    margins = [e / r for e, r in zip(ebit, rev)]
    capex_int = [c / r for c, r in zip(h["capex"], rev)]
    nwc_int = [n / r for n, r in zip(h["nwc_balance"], rev)]
    growth = [rev[k] / rev[k - 1] - 1 for k in range(1, nh)]

    def stat(xs):
        return {"min": min(xs), "max": max(xs), "avg": sum(xs) / len(xs),
                "last": xs[-1]}

    return {
        "years": nh,
        "revenue_cagr": cagr(rev, nh - 1),
        "revenue_growth": stat(growth),
        "ebit_margin": stat(margins),
        "capex_pct_rev": stat(capex_int),
        "nwc_pct_rev": stat(nwc_int),
        "down_years": sum(1 for g in growth if g < 0),
    }


def assumption_flags(spec: Dict[str, Any]) -> List[str]:
    """Flag forecast drivers that sit outside anything in the history."""
    s = history_stats(spec)
    i = spec["inputs"]
    out = []
    checks = [
        ("ebit_margin", "EBIT margin", s["ebit_margin"]),
        ("capex_pct_rev", "capex intensity", s["capex_pct_rev"]),
        ("nwc_pct_rev", "working capital intensity", s["nwc_pct_rev"]),
        ("rev_growth", "revenue growth", s["revenue_growth"]),
    ]
    for key, lab, st in checks:
        for t, val in enumerate(i[key]):
            if val > st["max"] * 1.0001:
                out.append(
                    f"{lab} in year {t+1} ({val:.1%}) is above the {s['years']}-year "
                    f"high of {st['max']:.1%} -- justify it or bring it down")
                break
            if val < st["min"] * 0.9999 and key in ("ebit_margin", "rev_growth"):
                out.append(
                    f"{lab} in year {t+1} ({val:.1%}) is below the {s['years']}-year "
                    f"low of {st['min']:.1%} -- say why")
                break
    return out


# --------------------------------------------------------------------------
# sensitivity helpers
# --------------------------------------------------------------------------

SHIFTABLE = {
    "wacc": ("derived", "scalar"),
    "terminal_growth": ("inputs.terminal_growth", "scalar"),
    "tax_rate": ("inputs.tax_rate", "scalar"),
    "beta": ("inputs.beta", "scalar"),
    "exit_multiple": ("inputs.exit_multiple", "scalar"),
    "rev_growth": ("inputs.rev_growth", "vector"),
    "ebit_margin": ("inputs.ebit_margin", "vector"),
    "da_pct_rev": ("inputs.da_pct_rev", "vector"),
    "capex_pct_rev": ("inputs.capex_pct_rev", "vector"),
    "nwc_pct_rev": ("inputs.nwc_pct_rev", "vector"),
}


def perturb(spec: Dict[str, Any], key: str, rel: float) -> Dict[str, Any]:
    s = copy.deepcopy(spec)
    if key == "wacc":
        base = wacc(spec)
        s["inputs"]["risk_free"] += base * (1 + rel) - base
        return s
    path, kind = SHIFTABLE[key]
    field_name = path.split(".")[1]
    if kind == "scalar":
        s["inputs"][field_name] *= 1 + rel
    else:
        s["inputs"][field_name] = [x * (1 + rel) for x in s["inputs"][field_name]]
    return s


def scan(spec: Dict[str, Any], rel: float = 0.10) -> List[Dict[str, Any]]:
    base = run(spec).value_per_share
    rows = []
    for key in SHIFTABLE:
        try:
            up = run(perturb(spec, key, rel)).value_per_share
            down = run(perturb(spec, key, -rel)).value_per_share
        except (SpecError, ZeroDivisionError):
            continue
        swing = abs(up - down)
        rows.append({"input": key, "base": base, "up": up, "down": down,
                     "swing": swing,
                     "swing_pct": swing / base if base else float("nan")})
    rows.sort(key=lambda r: r["swing"], reverse=True)
    return rows


def _valid_value(spec: Dict[str, Any], key: str, rel: float):
    """Value per share at a perturbation, or None where the model is undefined.

    The perpetuity formula diverges as terminal growth approaches WACC and
    inverts beyond it, which produces spurious roots -- a naive bisection
    will happily report that raising terminal growth lowers the valuation.
    """
    try:
        s = perturb(spec, key, rel)
        if s["inputs"]["terminal_growth"] >= wacc(s) - 1e-6:
            return None
        v = run(s)
    except (SpecError, ZeroDivisionError, OverflowError):
        return None
    if v.value_per_share != v.value_per_share:
        return None
    return v.value_per_share


def breakeven(spec: Dict[str, Any], key: str, target_move: float = 0.30,
              lo: float = -0.95, hi: float = 5.0, points: int = 601,
              tol: float = 1e-7) -> Dict[str, Any]:
    """Smallest change in `key` that moves value per share by target_move."""
    base = run(spec).value_per_share
    out: Dict[str, Any] = {"input": key, "base_value": base,
                           "target_move": target_move}
    grid = [lo + (hi - lo) * k / (points - 1) for k in range(points)]
    samples = [(r, _valid_value(spec, key, r)) for r in grid]

    for direction, goal in (("up", base * (1 + target_move)),
                            ("down", base * (1 - target_move))):
        brackets = []
        for (r0, v0), (r1, v1) in zip(samples, samples[1:]):
            if v0 is None or v1 is None:
                continue
            f0, f1 = v0 - goal, v1 - goal
            if f0 == 0:
                brackets.append((r0, r0))
            elif f0 * f1 < 0:
                brackets.append((r0, r1))
        if not brackets:
            out[direction] = None
            continue
        a, b = min(brackets, key=lambda br: min(abs(br[0]), abs(br[1])))
        fa = _valid_value(spec, key, a) - goal
        for _ in range(100):
            m = (a + b) / 2
            vm = _valid_value(spec, key, m)
            if vm is None:
                break
            fm = vm - goal
            if abs(fm) < tol or (b - a) < 1e-9:
                a = b = m
                break
            if fa * fm <= 0:
                b = m
            else:
                a, fa = m, fm
        out[direction] = (a + b) / 2
    return out


# --------------------------------------------------------------------------
# shared return maths, used by the LBO engine too
# --------------------------------------------------------------------------


def irr(cashflows: List[float], lo: float = -0.9999, hi: float = 10.0,
        tol: float = 1e-10) -> float:
    """IRR by bisection on NPV. Returns nan where no sign change exists."""
    def npv(r):
        return sum(cf / (1 + r) ** t for t, cf in enumerate(cashflows))

    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return float("nan")
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2
