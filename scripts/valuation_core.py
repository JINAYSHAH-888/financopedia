"""
Derived valuation inputs: WACC build-up, intrinsic growth, relative pricing,
scenarios.

Everything here replaces a number that would otherwise be asserted. A bare
"beta: 1.1" is an assertion; a peer set unlevered, re-levered at a target
capital structure and blended with a regression estimate is an argument you
can audit. Same for the equity risk premium (from a market return history
rather than a round number), the cost of debt (from interest actually paid),
and the growth rate (from what the company reinvests and what it earns on
that reinvestment).

Each function returns the whole working, not just the answer, so the workbook
can show the derivation and the auditor can check every step.
"""

from __future__ import annotations

from typing import Any, Dict, List

from dcf_core import SpecError


# --------------------------------------------------------------------------
# small statistics -- matching Excel's conventions exactly
# --------------------------------------------------------------------------


def median(xs: List[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def quartile_exc(xs: List[float], q: int) -> float:
    """Excel's QUARTILE.EXC, which is what sell-side comp sheets use.

    Differs from the inclusive version: with ten peers the 25th percentile is
    an interpolated point below the second observation, not the second
    observation itself. Matching it matters because the workbook and this
    engine must agree to 1e-6.
    """
    s = sorted(xs)
    n = len(s)
    h = q * (n + 1) / 4.0
    if h < 1 or h > n:
        return float("nan")
    lo = int(h)
    frac = h - lo
    if lo >= n:
        return s[n - 1]
    return s[lo - 1] + frac * (s[lo] - s[lo - 1])


# --------------------------------------------------------------------------
# WACC build-up
# --------------------------------------------------------------------------

WACC_REQUIRED = ["risk_free", "marginal_tax_rate", "beta_source"]


def has_buildup(spec: Dict[str, Any]) -> bool:
    return bool(spec.get("wacc_build"))


def validate_wacc(spec: Dict[str, Any], problems: List[str]) -> None:
    w = spec.get("wacc_build")
    if not w:
        return
    for key in WACC_REQUIRED:
        if key not in w:
            problems.append(f"wacc_build.{key} is required")
    src = w.get("beta_source")
    if src not in (None, "comps", "regression", "average"):
        problems.append("wacc_build.beta_source must be comps, regression or average")

    if src in ("comps", "average") and not w.get("peers"):
        problems.append("wacc_build.peers is required when beta comes from comps")
    for k, p in enumerate(w.get("peers", [])):
        for key in ("name", "total_debt", "total_equity", "levered_beta",
                    "tax_rate"):
            if key not in p:
                problems.append(f"wacc_build.peers[{k}].{key} is required")
        if not p.get("source"):
            problems.append(f"wacc_build.peers[{k}].source is required")

    if src in ("regression", "average"):
        reg = w.get("regression_beta")
        if not reg or not ("raw_beta" in reg or reg.get("prices")):
            problems.append("wacc_build.regression_beta needs either a price "
                            "series (prices) to regress or an asserted raw_beta "
                            "when beta comes from a regression")
        elif not reg.get("source"):
            problems.append("wacc_build.regression_beta.source is required — "
                            "say what was regressed against what, over what period")

    mr = w.get("market_returns")
    if mr:
        if len(mr.get("years", [])) != len(mr.get("returns", [])):
            problems.append("wacc_build.market_returns years and returns must "
                            "be the same length")
        if len(mr.get("returns", [])) < 10:
            problems.append("wacc_build.market_returns needs at least 10 years — "
                            "a short window gives an equity risk premium that is "
                            "mostly noise")
        if not mr.get("source"):
            problems.append("wacc_build.market_returns.source is required")
    elif "equity_risk_premium" not in w:
        problems.append("wacc_build needs either market_returns (to derive the "
                        "equity risk premium) or an explicit equity_risk_premium")

    cod = w.get("cost_of_debt")
    if not cod:
        problems.append("wacc_build.cost_of_debt is required")
    else:
        if cod.get("method") == "interest_over_debt":
            for key in ("interest_expense", "total_debt"):
                if key not in cod:
                    problems.append(f"wacc_build.cost_of_debt.{key} is required "
                                    "for the interest_over_debt method")
        elif "rate" not in cod:
            problems.append("wacc_build.cost_of_debt.rate is required when the "
                            "method is not interest_over_debt")
        if not cod.get("source"):
            problems.append("wacc_build.cost_of_debt.source is required")


def unlever(levered_beta: float, tax: float, debt: float, equity: float) -> float:
    """Hamada: strip the peer's financial leverage out of its observed beta."""
    de = debt / equity if equity else 0.0
    return levered_beta / (1 + (1 - tax) * de)


def relever(unlevered_beta: float, tax: float, de: float) -> float:
    return unlevered_beta * (1 + (1 - tax) * de)


def wacc_buildup(spec: Dict[str, Any]) -> Dict[str, Any]:
    w = spec["wacc_build"]
    out: Dict[str, Any] = {}

    peers = w.get("peers", [])
    out["peer_de"] = [p["total_debt"] / p["total_equity"] for p in peers]
    out["peer_dc"] = [p["total_debt"] / (p["total_debt"] + p["total_equity"])
                      for p in peers]
    out["peer_unlevered"] = [
        unlever(p["levered_beta"], p["tax_rate"], p["total_debt"], p["total_equity"])
        for p in peers]
    out["median_unlevered"] = median(out["peer_unlevered"]) if peers else float("nan")
    out["median_de"] = median(out["peer_de"]) if peers else float("nan")
    out["mean_dc"] = mean(out["peer_dc"]) if peers else float("nan")

    tax = w["marginal_tax_rate"]
    target_de = w.get("target_debt_equity", out["median_de"])
    out["target_de"] = target_de
    out["target_debt_weight"] = w.get(
        "target_debt_weight", target_de / (1 + target_de) if target_de == target_de
        else float("nan"))
    out["relevered_beta"] = (relever(out["median_unlevered"], tax, target_de)
                             if peers else float("nan"))

    reg = w.get("regression_beta") or {}
    raw = raw_beta(spec)
    weight = reg.get("blume_weight_raw", 0.75)
    out["raw_beta"] = raw
    out["blume_weight_raw"] = weight
    out["adjusted_beta"] = (weight * raw + (1 - weight) * 1.0
                            if raw is not None else float("nan"))

    src = w["beta_source"]
    if src == "comps":
        out["beta"] = out["relevered_beta"]
    elif src == "regression":
        out["beta"] = out["adjusted_beta"]
    else:
        out["beta"] = (out["relevered_beta"] + out["adjusted_beta"]) / 2
    out["beta_source"] = src

    rf = w["risk_free"]
    out["risk_free"] = rf
    mr = w.get("market_returns")
    if mr:
        out["market_return_avg"] = mean(mr["returns"])
        out["dividend_yield"] = mr.get("dividend_yield", 0.0)
        out["market_return_total"] = out["market_return_avg"] + out["dividend_yield"]
        out["equity_risk_premium"] = out["market_return_total"] - rf
        out["erp_years"] = len(mr["returns"])
    else:
        out["market_return_avg"] = float("nan")
        out["dividend_yield"] = float("nan")
        out["market_return_total"] = float("nan")
        out["equity_risk_premium"] = w["equity_risk_premium"]
        out["erp_years"] = 0

    out["cost_of_equity"] = rf + out["beta"] * out["equity_risk_premium"]

    cod = w["cost_of_debt"]
    if cod.get("method") == "interest_over_debt":
        out["pre_tax_cost_of_debt"] = (cod["interest_expense"] / cod["total_debt"]
                                       if cod["total_debt"] else float("nan"))
    else:
        out["pre_tax_cost_of_debt"] = cod["rate"]
    out["marginal_tax_rate"] = tax
    out["after_tax_cost_of_debt"] = out["pre_tax_cost_of_debt"] * (1 - tax)

    wd = out["target_debt_weight"]
    out["debt_weight"] = wd
    out["equity_weight"] = 1 - wd
    out["wacc"] = (out["equity_weight"] * out["cost_of_equity"]
                   + wd * out["after_tax_cost_of_debt"])
    return out


# --------------------------------------------------------------------------
# beta from the return series
# --------------------------------------------------------------------------


def validate_regression(spec: Dict[str, Any], problems: List[str]) -> None:
    w = spec.get("wacc_build") or {}
    reg = w.get("regression_beta") or {}
    prices = reg.get("prices")
    if not prices:
        return
    n = len(prices.get("stock", []))
    if len(prices.get("index", [])) != n:
        problems.append("regression_beta.prices: stock and index series must be "
                        "the same length")
    if len(prices.get("dates", [])) not in (0, n):
        problems.append("regression_beta.prices.dates must match the price series")
    if n < 30:
        problems.append(f"regression_beta.prices has {n} observations; a beta "
                        "from fewer than 30 is mostly noise")
    if any(x <= 0 for x in prices.get("stock", []) + prices.get("index", [])):
        problems.append("regression_beta.prices contains a non-positive price")
    if not reg.get("source"):
        problems.append("regression_beta.source is required — say what was "
                        "regressed against what, over what period")


def regression_beta(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Ordinary least squares of stock returns on index returns.

    Returns slope, intercept, R² and the observation count — the same figures
    Excel's SLOPE, INTERCEPT, RSQ and COUNT produce, so the workbook and this
    engine can be compared cell for cell. R² is reported because a beta from a
    regression that explains little of the share's movement deserves less
    weight than one from a tight fit.
    """
    reg = spec["wacc_build"]["regression_beta"]
    p = reg["prices"]
    y = [p["stock"][k] / p["stock"][k - 1] - 1 for k in range(1, len(p["stock"]))]
    x = [p["index"][k] / p["index"][k - 1] - 1 for k in range(1, len(p["index"]))]
    n = len(y)
    mx, my = mean(x), mean(y)
    sxy = sum((x[k] - mx) * (y[k] - my) for k in range(n))
    sxx = sum((x[k] - mx) ** 2 for k in range(n))
    syy = sum((y[k] - my) ** 2 for k in range(n))
    slope = sxy / sxx if sxx else float("nan")
    return {
        "stock_returns": y, "index_returns": x, "observations": n,
        "slope": slope, "intercept": my - slope * mx,
        "r_squared": (sxy * sxy) / (sxx * syy) if sxx and syy else float("nan"),
        "frequency": reg.get("frequency", "weekly"),
    }


def raw_beta(spec: Dict[str, Any]) -> float:
    """The regression beta, computed from prices where they are supplied."""
    reg = (spec.get("wacc_build") or {}).get("regression_beta") or {}
    if reg.get("prices"):
        return regression_beta(spec)["slope"]
    return reg.get("raw_beta")


# --------------------------------------------------------------------------
# segment revenue build
# --------------------------------------------------------------------------


def validate_segments(spec: Dict[str, Any], problems: List[str]) -> None:
    segs = spec.get("segments")
    if not segs:
        return
    nh = len(spec["historicals"]["years"])
    nf = len(spec["inputs"]["rev_growth"])
    for k, sg in enumerate(segs):
        for key in ("name", "historical_revenue", "growth"):
            if key not in sg:
                problems.append(f"segments[{k}].{key} is required")
        if len(sg.get("historical_revenue", [])) not in (0, nh):
            problems.append(f"segments[{k}].historical_revenue must have one "
                            f"entry per historical year ({nh})")
        if len(sg.get("growth", [])) not in (0, nf):
            problems.append(f"segments[{k}].growth must have one entry per "
                            f"forecast year ({nf})")
        if not sg.get("source"):
            problems.append(f"segments[{k}].source is required")
        if not sg.get("basis"):
            problems.append(f"segments[{k}].basis is required — say where the "
                            "growth path came from")
    if problems:
        return
    # the transcription check: segments must add up to reported revenue
    off = []
    for t in range(nh):
        total = sum(sg["historical_revenue"][t] for sg in segs)
        reported = spec["historicals"]["revenue"][t]
        if abs(total - reported) / max(abs(reported), 1.0) > 1e-4:
            off.append(f"{spec['historicals']['years'][t]}: segments sum to "
                       f"{total:,.1f} vs reported revenue {reported:,.1f}")
    if off:
        problems.append("segment revenue does not reconcile to reported revenue "
                        "-- almost always a missing segment or a restatement:\n      "
                        + "\n      ".join(off))


def segment_build(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Forecast each segment on its own growth path; the top line is the sum.

    The blended growth rate then stops being an assumption and becomes a
    consequence: a mix shift toward a faster-growing segment lifts group growth
    without anyone having to assert that it does.
    """
    segs = spec["segments"]
    nh = len(spec["historicals"]["years"])
    nf = len(segs[0]["growth"])

    hist_totals = [sum(sg["historical_revenue"][t] for sg in segs)
                   for t in range(nh)]
    rows, prev = [], {}
    for sg in segs:
        prev[sg["name"]] = sg["historical_revenue"][-1]
    forecast = {sg["name"]: [] for sg in segs}
    for t in range(nf):
        for sg in segs:
            val = prev[sg["name"]] * (1 + sg["growth"][t])
            forecast[sg["name"]].append(val)
            prev[sg["name"]] = val
    totals = [sum(forecast[sg["name"]][t] for sg in segs) for t in range(nf)]

    implied = []
    for t in range(nf):
        base = hist_totals[-1] if t == 0 else totals[t - 1]
        implied.append(totals[t] / base - 1)

    hist_mix = [[sg["historical_revenue"][t] / hist_totals[t] for sg in segs]
                for t in range(nh)]
    fcst_mix = [[forecast[sg["name"]][t] / totals[t] for sg in segs]
                for t in range(nf)]
    return {"hist_totals": hist_totals, "forecast": forecast, "totals": totals,
            "implied_growth": implied, "hist_mix": hist_mix,
            "fcst_mix": fcst_mix, "names": [sg["name"] for sg in segs]}


def apply_segments(spec: Dict[str, Any]) -> None:
    """Overwrite the revenue growth path with the one the segments imply.

    Done once, at validation, so every downstream consumer -- the projection,
    the sensitivity grid, the scenarios -- sees one growth path and cannot
    disagree with the segment tab about what it is.
    """
    if spec.get("segments"):
        spec["inputs"]["rev_growth"] = segment_build(spec)["implied_growth"]


# --------------------------------------------------------------------------
# intrinsic growth: what the company can actually grow at
# --------------------------------------------------------------------------


def validate_intrinsic(spec: Dict[str, Any], problems: List[str]) -> None:
    h = spec.get("historicals", {})
    if "ppe_net" not in h:
        problems.append("historicals.ppe_net is required — invested capital, and "
                        "so ROIC and intrinsic growth, cannot be computed without it")
    elif len(h["ppe_net"]) != len(h.get("years", [])):
        problems.append("historicals.ppe_net must have one entry per historical year")
    elif not h.get("sources", {}).get("ppe_net"):
        problems.append("historicals.sources.ppe_net is required")


def intrinsic_growth(spec: Dict[str, Any]) -> Dict[str, Any]:
    """g = reinvestment rate x ROIC, from the last two reported years.

    This is the growth the business can fund from what it actually earns and
    reinvests. It is not a forecast; it is a benchmark to judge a forecast
    against. A projection well above it is assuming either margin expansion or
    capital efficiency the record does not show.
    """
    h = spec["historicals"]
    tax = (spec.get("wacc_build", {}).get("marginal_tax_rate")
           or spec["inputs"]["tax_rate"])

    ic = [h["ppe_net"][t] + h["nwc_balance"][t] for t in range(len(h["years"]))]
    nopat = [h["ebit"][t] * (1 - tax) for t in range(len(h["years"]))]
    roic = [nopat[t] / ic[t] if ic[t] else float("nan") for t in range(len(ic))]

    net_capex = h["capex"][-1] - h["da"][-1]
    delta_nwc = h["nwc_balance"][-1] - h["nwc_balance"][-2]
    reinvestment = net_capex + delta_nwc
    rr = reinvestment / nopat[-1] if nopat[-1] else float("nan")

    return {
        "invested_capital": ic,
        "nopat": nopat,
        "roic": roic,
        "roic_latest": roic[-1],
        "roic_avg": mean([r for r in roic if r == r]),
        "net_capex": net_capex,
        "delta_nwc": delta_nwc,
        "reinvestment": reinvestment,
        "reinvestment_rate": rr,
        "intrinsic_growth": rr * roic[-1],
        "tax_rate": tax,
    }


# --------------------------------------------------------------------------
# relative pricing: the full peer distribution, not one median
# --------------------------------------------------------------------------

REL_METRICS = ["ev_revenue", "ev_ebitda", "pe"]


def validate_relative(spec: Dict[str, Any], problems: List[str]) -> None:
    peers = spec.get("relative_peers")
    if not peers:
        return
    for k, p in enumerate(peers):
        for key in ("name", "share_price", "shares_out", "total_debt", "cash",
                    "revenue", "ebitda", "net_income"):
            if key not in p:
                problems.append(f"relative_peers[{k}].{key} is required")
        if not p.get("source"):
            problems.append(f"relative_peers[{k}].source is required")
    if len(peers) < 4:
        problems.append("relative_peers needs at least 4 peers for quartiles to "
                        "mean anything")


def relative_pricing(spec: Dict[str, Any]) -> Dict[str, Any]:
    peers = spec["relative_peers"]
    rows = []
    for p in peers:
        equity = p["share_price"] * p["shares_out"]
        net_debt = p["total_debt"] - p["cash"]
        ev = equity + net_debt
        rows.append({
            "name": p["name"], "equity_value": equity, "net_debt": net_debt,
            "ev": ev,
            "ev_revenue": ev / p["revenue"] if p["revenue"] else float("nan"),
            "ev_ebitda": ev / p["ebitda"] if p["ebitda"] else float("nan"),
            "pe": equity / p["net_income"] if p["net_income"] else float("nan"),
        })

    stats = {}
    for m in REL_METRICS:
        xs = [r[m] for r in rows if r[m] == r[m]]
        stats[m] = {
            "high": max(xs), "p75": quartile_exc(xs, 3), "mean": mean(xs),
            "median": median(xs), "p25": quartile_exc(xs, 1), "low": min(xs),
        }

    sub = spec["subject"]
    net_debt = sub["net_debt"]
    shares = sub["shares_out"]
    implied = {}
    for m, driver in (("ev_revenue", sub["revenue"]),
                      ("ev_ebitda", sub["ebitda"]),
                      ("pe", sub["net_income"])):
        band = {}
        for stat in ("p25", "median", "p75"):
            mult = stats[m][stat]
            if m == "pe":
                equity = mult * driver
            else:
                equity = mult * driver - net_debt
            band[stat] = equity / shares
        implied[m] = band
    return {"rows": rows, "stats": stats, "implied": implied}


# --------------------------------------------------------------------------
# scenarios
# --------------------------------------------------------------------------


def scenario_values(spec: Dict[str, Any]) -> Dict[str, float]:
    """Bear / base / bull as a parallel shift to the revenue growth path."""
    import copy

    import dcf_core as core

    delta = spec["inputs"].get("scenario_growth_delta", 0.02)
    out = {}
    for name, shift in (("bear", -delta), ("base", 0.0), ("bull", delta)):
        s = copy.deepcopy(spec)
        s["inputs"]["rev_growth"] = [g + shift for g in s["inputs"]["rev_growth"]]
        out[name] = core.run(s).value_per_share
    out["delta"] = delta
    return out
