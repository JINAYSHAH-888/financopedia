#!/usr/bin/env python3
"""
Financopedia model auditor.

Recalculates the workbook headlessly through LibreOffice and checks it
against an independent engine computed in Python from the same spec. The two
implementations are written separately; a transcription error in the Excel
formulas shows up here as a mismatch rather than as a plausible wrong number.

    python3 audit_model.py TICK-dcf.xlsx        --spec SPEC.json --type dcf
    python3 audit_model.py TICK-statements.xlsx --spec SPEC.json --type statements
    python3 audit_model.py TICK-lbo.xlsx        --spec SPEC.json --type lbo
    python3 audit_model.py TICK-ipo.xlsx        --spec SPEC.json --type ipo

Exit code 0 means every check passed and the file can be delivered.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dcf_core as core  # noqa: E402
from audit_lib import (Audit, close, compare, formula_cells_only, getv,  # noqa: E402
                       no_error_values, open_pair, workbook_checks_tab)
from build_model import CELLS, GRID, basis_col  # noqa: E402
from xl_style import col  # noqa: E402


# --------------------------------------------------------------------------
# shared spec-level gates
# --------------------------------------------------------------------------


def check_tabs(a, wb_f, needed):
    missing = [s for s in needed if s not in wb_f.sheetnames]
    return a.check("All required tabs present", not missing,
                   f"missing: {missing}" if missing else "/".join(needed))


def check_history_sourced(a, ws, rows, src_col, keys):
    missing = [k for k in keys
               if not str(ws.cell(row=rows[k], column=src_col).value or "").strip()]
    return a.check("Every historical row carries a filing source", not missing,
                   f"missing: {missing}" if missing
                   else f"{len(keys)}/{len(keys)} rows sourced")


def check_hist_values(a, ws, spec, rows, keys):
    nh = core.n_hist(spec)
    bad = []
    for key in keys:
        for t in range(nh):
            got = ws[f"{col(2 + t)}{rows[key]}"].value
            want = spec["historicals"][key][t]
            if not isinstance(got, (int, float)) or not close(float(got), float(want)):
                bad.append(f"{key}[{t}]")
    return a.check("HISTORICALS match the spec exactly", not bad,
                   f"mismatches: {bad[:5]}" if bad
                   else f"{len(keys)} metrics x {nh} years")


# --------------------------------------------------------------------------
# DCF
# --------------------------------------------------------------------------


def audit_dcf(a, path, spec):
    expected = core.run(spec)
    nh, nf = core.n_hist(spec), core.n_fcst(spec)
    P, V, H, I, S = (CELLS["PROJECTION"], CELLS["VALUATION"],
                     CELLS["HISTORICALS"], CELLS["INPUTS"], CELLS["SENSITIVITY"])
    flast = col(1 + nf)

    wb_f, wbv, tmp = open_pair(path)
    a.check("Workbook recalculates in LibreOffice", True, "headless round-trip")
    check_tabs(a, wb_f, ["README", "INPUTS", "HISTORICALS", "PROJECTION",
                         "VALUATION", "SENSITIVITY", "CHECKS"])
    a.info("Horizons", f"{nh} historical years, {nf} forecast years")

    # WACC and RELATIVE_PRICING are input tabs: they carry sourced peer data,
    # so the hardcode scan covers the calculation tabs only
    formula_cells_only(a, wb_f, ["PROJECTION", "VALUATION", "SENSITIVITY",
                                 "INTRINSIC_GROWTH", "SCENARIOS"])

    ws = wb_f["PROJECTION"]
    gaps = [f"{col(2 + t)}{P[k]}" for k in
            ("revenue", "ebit", "tax", "nopat", "da", "capex", "nwc_balance",
             "delta_nwc", "fcf") for t in range(nf)
            if not str(ws[f"{col(2 + t)}{P[k]}"].value or "").startswith("=")]
    a.check("Projection is 100% formulas", not gaps,
            f"{len(gaps)} non-formula cells: {gaps[:5]}" if gaps
            else f"{nf * 9} cells, all formulas")

    ws = wb_f["VALUATION"]
    gaps = [V[k] for k in ("pv_explicit", "terminal_value", "pv_terminal",
                           "enterprise_value", "equity_value", "value_per_share",
                           "value_per_share_exit", "value_per_share_comps")
            if not str(ws[V[k]].value or "").startswith("=")]
    a.check("Valuation bridge is 100% formulas", not gaps,
            f"non-formula: {gaps}" if gaps else "bridge, both cross-checks")

    ws = wb_f["SENSITIVITY"]
    gaps = [f"{col(S['grid_first_col'] + k)}{S['y_start'] + j}"
            for k in range(GRID) for j in range(GRID)
            if not str(ws[f"{col(S['grid_first_col'] + k)}"
                          f"{S['y_start'] + j}"].value or "").startswith("=")]
    a.check("Sensitivity grid is formula-driven off INPUTS", not gaps,
            f"non-formula: {gaps}" if gaps else f"{GRID}x{GRID} grid")

    ws = wb_f["INPUTS"]
    bad = []
    # scalars the WACC build-up derives are links, not inputs, and are checked
    # against the derivation instead
    derived = core.BUILDUP_SUPPLIED if spec.get("wacc_build") else set()
    for key in core.REQUIRED_SCALARS:
        if key in derived:
            continue
        got, want = ws[I[key]].value, spec["inputs"][key]
        if not isinstance(got, (int, float)) or not close(float(got), float(want)):
            bad.append(f"{key}: sheet={got} spec={want}")
    derived_vectors = {"rev_growth"} if spec.get("segments") else set()
    for key in core.REQUIRED_VECTORS:
        if key in derived_vectors:
            continue  # a link to the segment build; checked against it below
        for t in range(nf):
            got = ws[f"{col(2 + t)}{I[f'{key}_row']}"].value
            want = spec["inputs"][key][t]
            if not isinstance(got, (int, float)) or not close(float(got), float(want)):
                bad.append(f"{key}[{t}]")
    a.check("INPUTS match the spec exactly", not bad, "; ".join(bad[:4]) if bad
            else f"{len(core.REQUIRED_SCALARS) - len(derived)} scalars + "
                 f"{len(core.REQUIRED_VECTORS) * nf} driver cells"
                 + (f" ({len(derived)} derived on the WACC tab)" if derived else ""))

    hkeys = ["revenue", "ebit", "da", "capex", "nwc_balance", "ppe_net"]
    check_hist_values(a, wb_f["HISTORICALS"], spec, H, hkeys)
    check_history_sourced(a, wb_f["HISTORICALS"], H, 2 + nh, hkeys)

    bcol = basis_col(nf)
    no_basis = [k for k in core.REQUIRED_SCALARS
                if k not in core.PRESENTATION_INPUTS and k not in derived
                and not str(ws.cell(row=int(I[k][1:]), column=bcol).value or "").strip()]
    no_basis += [k for k in core.REQUIRED_VECTORS
                 if not str(ws.cell(row=I[f"{k}_row"], column=bcol).value or "").strip()]
    a.check("Every assumption states its basis", not no_basis,
            f"missing: {no_basis}" if no_basis else "all assumptions annotated")

    a.info("Estimated inputs (amber in the workbook)",
           ", ".join(spec["inputs"].get("estimates", [])) or "none declared")

    flags = core.assumption_flags(spec)
    a.check("Forecast drivers sit inside the historical range", not flags,
            flags[0] if flags else f"checked against {nh} years of history")

    no_error_values(a, wbv)

    compare(a, "Workbook outputs match the independent Python model", [
        ("WACC", getv(wbv, "INPUTS", I["wacc"]), expected.wacc),
        ("PV of explicit FCF", getv(wbv, "VALUATION", V["pv_explicit"]),
         expected.pv_explicit),
        ("Terminal value", getv(wbv, "VALUATION", V["terminal_value"]),
         expected.terminal_value),
        ("Enterprise value", getv(wbv, "VALUATION", V["enterprise_value"]),
         expected.enterprise_value),
        ("Equity value", getv(wbv, "VALUATION", V["equity_value"]),
         expected.equity_value),
        ("Value per share", getv(wbv, "VALUATION", V["value_per_share"]),
         expected.value_per_share),
        ("Value per share (exit)", getv(wbv, "VALUATION", V["value_per_share_exit"]),
         expected.value_per_share_exit),
    ])

    compare(a, "Projected free cash flows match year by year",
            [(f"Y{t+1}", getv(wbv, "PROJECTION", f"{col(2 + t)}{P['fcf']}"),
              expected.fcf[t]) for t in range(nf)], fmt="{:,.1f}")

    hs = core.history_stats(spec)
    compare(a, "Historical statistics block matches the data", [
        ("CAGR", getv(wbv, "HISTORICALS", f"B{H['cagr']}"), hs["revenue_cagr"]),
        ("avg margin", getv(wbv, "HISTORICALS", f"B{H['margin_avg']}"),
         hs["ebit_margin"]["avg"]),
        ("max margin", getv(wbv, "HISTORICALS", f"B{H['margin_max']}"),
         hs["ebit_margin"]["max"]),
        ("down years", getv(wbv, "HISTORICALS", f"B{H['down_years']}"),
         float(hs["down_years"])),
    ], fmt="{:,.4f}")

    cc = col(S["grid_first_col"] + GRID // 2)
    centre = getv(wbv, "SENSITIVITY", f"{cc}{S['y_start'] + GRID // 2}")
    a.check("Sensitivity centre equals the base valuation",
            close(centre, expected.value_per_share, 1e-4),
            f"grid centre {centre:,.4f} vs base {expected.value_per_share:,.4f}"
            if centre is not None else "grid centre is blank")

    cells = [getv(wbv, "SENSITIVITY", f"{col(S['grid_first_col'] + k)}"
                  f"{S['y_start'] + j}") for k in range(GRID) for j in range(GRID)]
    cells = [c for c in cells if c is not None]
    a.check("Sensitivity grid actually varies",
            len({round(c, 6) for c in cells}) > 1,
            f"{len(cells)} live cells, range {min(cells):,.2f}–{max(cells):,.2f}"
            if cells else "grid produced no values")

    audit_dcf_extras(a, wbv, wb_f, spec)
    workbook_checks_tab(a, wbv)
    shutil.rmtree(tmp, ignore_errors=True)
    return a


def audit_dcf_extras(a, wbv, wb_f, spec):
    """The derivation tabs: WACC build-up, intrinsic growth, relative pricing,
    scenarios, football field."""
    import build_dcf_extras as ex
    import valuation_core as vc

    nf = core.n_fcst(spec)

    if spec.get("wacc_build"):
        w = vc.wacc_buildup(spec)
        wb_ = spec["wacc_build"]
        R = ex.erp_rows(ex.wacc_rows(len(wb_.get("peers", []))),
                        len(wb_.get("market_returns", {}).get("years", [])))
        a.check("WACC tab present", "WACC" in wb_f.sheetnames, "derivation shown")
        compare(a, "WACC build-up matches the Python engine", [
            ("median unlevered beta",
             getv(wbv, "WACC", f"H{R['median']}"), w["median_unlevered"]),
            ("re-levered beta", getv(wbv, "WACC", f"B{R['relevered']}"),
             w["relevered_beta"]),
            ("Blume-adjusted beta", getv(wbv, "WACC", f"B{R['adjusted_beta']}"),
             w["adjusted_beta"]),
            ("beta used", getv(wbv, "WACC", f"B{R['beta_used']}"), w["beta"]),
            ("equity risk premium", getv(wbv, "WACC", f"B{R['erp']}"),
             w["equity_risk_premium"]),
            ("pre-tax cost of debt", getv(wbv, "WACC", f"B{R['pre_tax_kd']}"),
             w["pre_tax_cost_of_debt"]),
            ("cost of equity", getv(wbv, "WACC", f"B{R['cost_of_equity']}"),
             w["cost_of_equity"]),
            ("WACC", getv(wbv, "WACC", f"B{R['wacc']}"), w["wacc"]),
        ], fmt="{:,.5f}")
        linked = getv(wbv, "INPUTS", CELLS["INPUTS"]["wacc"])
        a.check("INPUTS takes its WACC from the derivation",
                close(linked, w["wacc"]),
                "one number, one home — no second hardcoded WACC"
                if close(linked, w["wacc"]) else
                f"INPUTS {linked} vs WACC tab {w['wacc']}")
        a.info("Equity risk premium window",
               f"{w['erp_years']} years of market returns")

    if spec.get("segments"):
        sb = vc.segment_build(spec)
        SG = ex.seg_rows(len(spec["segments"]))
        nh = core.n_hist(spec)
        diffs = [getv(wbv, "SEGMENTS", f"{col(2 + t)}{SG['check']}")
                 for t in range(nh)]
        worst = max((abs(d) for d in diffs if d is not None), default=None)
        a.check("Segments reconcile to reported revenue in every year",
                worst is not None and worst < 0.01,
                f"worst gap {worst:,.6f} across {nh} years"
                if worst is not None else "no values")
        compare(a, "Segment build matches the Python engine",
                [(f"total Y{t+1}",
                  getv(wbv, "SEGMENTS", f"{col(2 + nh + t)}{SG['total']}"),
                  sb["totals"][t]) for t in range(nf)], fmt="{:,.1f}")
        compare(a, "Implied group growth matches the segment mix",
                [(f"Y{t+1}",
                  getv(wbv, "SEGMENTS", f"{col(2 + nh + t)}{SG['implied']}"),
                  sb["implied_growth"][t]) for t in range(nf)], fmt="{:,.5f}")
        linked = [getv(wbv, "INPUTS", f"{col(2 + t)}{CELLS['INPUTS']['rev_growth_row']}")
                  for t in range(nf)]
        ok = all(close(linked[t], sb["implied_growth"][t]) for t in range(nf))
        a.check("INPUTS takes its growth path from the segment build", ok,
                "one growth path, derived from the mix" if ok
                else f"INPUTS {linked[:3]} vs segments {sb['implied_growth'][:3]}")
        a.info("Revenue mix shift",
               " · ".join(f"{n} {sb['hist_mix'][-1][k]:.0%}→{sb['fcst_mix'][-1][k]:.0%}"
                          for k, n in enumerate(sb["names"])))

    reg_prices = (spec.get("wacc_build") or {}).get("regression_beta", {}).get("prices")
    if reg_prices:
        rb = vc.regression_beta(spec)
        BS = ex.br_stats_rows()
        compare(a, "Beta regression matches the Python engine", [
            ("observations", getv(wbv, "BETA_REGRESSION", f"H{BS['observations']}"),
             float(rb["observations"])),
            ("slope (raw beta)", getv(wbv, "BETA_REGRESSION", f"H{BS['slope']}"),
             rb["slope"]),
            ("intercept", getv(wbv, "BETA_REGRESSION", f"H{BS['intercept']}"),
             rb["intercept"]),
            ("R²", getv(wbv, "BETA_REGRESSION", f"H{BS['r_squared']}"),
             rb["r_squared"]),
        ], fmt="{:,.6f}")
        wr = ex.erp_rows(ex.wacc_rows(len(spec["wacc_build"].get("peers", []))),
                         len(spec["wacc_build"].get("market_returns", {}).get("years", [])))
        linked = getv(wbv, "WACC", f"B{wr['raw_beta']}")
        a.check("WACC takes its raw beta from the regression",
                close(linked, rb["slope"]),
                "no second hardcoded beta" if close(linked, rb["slope"])
                else f"WACC {linked} vs regression {rb['slope']}")
        a.info("Regression quality",
               f"R² {rb['r_squared']:.2f} over {rb['observations']} "
               f"{rb['frequency']} observations"
               + (" — low, so the peer-derived beta deserves more weight"
                  if rb["r_squared"] < 0.4 else ""))

    g = vc.intrinsic_growth(spec)
    compare(a, "Intrinsic growth matches the Python engine", [
        ("ROIC (latest)", getv(wbv, "INTRINSIC_GROWTH",
                               f"B{ex.IG['roic_used']}"), g["roic_latest"]),
        ("reinvestment rate", getv(wbv, "INTRINSIC_GROWTH",
                                   f"B{ex.IG['reinvestment_rate']}"),
         g["reinvestment_rate"]),
        ("intrinsic growth", getv(wbv, "INTRINSIC_GROWTH",
                                  f"B{ex.IG['intrinsic_growth']}"),
         g["intrinsic_growth"]),
    ], fmt="{:,.5f}")
    assumed = spec["inputs"]["rev_growth"][0]
    # A judgement item, not a defect: growing faster than RR x ROIC is allowed,
    # it just has to be paid for and explained. The gate reports it; the memo
    # answers it.
    if assumed <= g["intrinsic_growth"] + 1e-9:
        a.info("Year-1 growth vs intrinsic growth",
               f"assumed {assumed:.1%}, within intrinsic {g['intrinsic_growth']:.1%}")
    else:
        a.info("Year-1 growth vs intrinsic growth",
               f"assumed {assumed:.1%} ABOVE intrinsic {g['intrinsic_growth']:.1%} "
               "— the memo must say what funds the difference (margin expansion, "
               "capital efficiency, or acquisition)")

    if spec.get("relative_peers"):
        r = vc.relative_pricing(spec)
        RR = ex.rel_rows(len(spec["relative_peers"]))
        compare(a, "Relative pricing matches the Python engine", [
            ("EV/EBITDA p25", getv(wbv, "RELATIVE_PRICING", f"M{RR['p25']}"),
             r["stats"]["ev_ebitda"]["p25"]),
            ("EV/EBITDA median", getv(wbv, "RELATIVE_PRICING", f"M{RR['median']}"),
             r["stats"]["ev_ebitda"]["median"]),
            ("EV/EBITDA p75", getv(wbv, "RELATIVE_PRICING", f"M{RR['p75']}"),
             r["stats"]["ev_ebitda"]["p75"]),
            ("EV/Revenue median", getv(wbv, "RELATIVE_PRICING", f"L{RR['median']}"),
             r["stats"]["ev_revenue"]["median"]),
            ("P/E median", getv(wbv, "RELATIVE_PRICING", f"N{RR['median']}"),
             r["stats"]["pe"]["median"]),
            ("implied/share, EV/EBITDA median",
             getv(wbv, "RELATIVE_PRICING", f"M{RR['implied_median']}"),
             r["implied"]["ev_ebitda"]["median"]),
            ("implied/share, P/E p75",
             getv(wbv, "RELATIVE_PRICING", f"N{RR['implied_p75']}"),
             r["implied"]["pe"]["p75"]),
        ], fmt="{:,.4f}")

    sc = vc.scenario_values(spec)
    S = ex.scen_rows(nf)
    compare(a, "Scenarios match the Python engine", [
        ("bear", getv(wbv, "SCENARIOS", f"C{S['bear']}"), sc["bear"]),
        ("base", getv(wbv, "SCENARIOS", f"C{S['base']}"), sc["base"]),
        ("bull", getv(wbv, "SCENARIOS", f"C{S['bull']}"), sc["bull"]),
    ], fmt="{:,.4f}")
    bear = getv(wbv, "SCENARIOS", f"C{S['bear']}")
    bull = getv(wbv, "SCENARIOS", f"C{S['bull']}")
    base = getv(wbv, "SCENARIOS", f"C{S['base']}")
    a.check("Scenarios ordered bear < base < bull",
            None not in (bear, base, bull) and bear < base < bull,
            f"{bear:,.2f} < {base:,.2f} < {bull:,.2f}"
            if None not in (bear, base, bull) else "missing values")

    if spec.get("relative_peers") and "FOOTBALL_FIELD" in wb_f.sheetnames:
        bad = []
        for k in range(6):
            row = ex.FF["first"] + k
            lo = getv(wbv, "FOOTBALL_FIELD", f"B{row}")
            hi = getv(wbv, "FOOTBALL_FIELD", f"C{row}")
            if lo is None or hi is None or hi < lo:
                bad.append(str(wb_f["FOOTBALL_FIELD"][f"A{row}"].value))
        a.check("Football field bands are well formed", not bad,
                f"low above high on: {bad}" if bad
                else "6 methods, every low below its high")

        # a well-formed band can still be the WRONG band, so check the values
        r = vc.relative_pricing(spec)
        F = ex.FF["first"]
        compare(a, "Football field bands carry the right numbers", [
            ("EV/Revenue low", getv(wbv, "FOOTBALL_FIELD", f"B{F}"),
             r["implied"]["ev_revenue"]["p25"]),
            ("EV/Revenue high", getv(wbv, "FOOTBALL_FIELD", f"C{F}"),
             r["implied"]["ev_revenue"]["p75"]),
            ("EV/EBITDA low", getv(wbv, "FOOTBALL_FIELD", f"B{F + 1}"),
             r["implied"]["ev_ebitda"]["p25"]),
            ("EV/EBITDA high", getv(wbv, "FOOTBALL_FIELD", f"C{F + 1}"),
             r["implied"]["ev_ebitda"]["p75"]),
            ("P/E low", getv(wbv, "FOOTBALL_FIELD", f"B{F + 2}"),
             r["implied"]["pe"]["p25"]),
            ("DCF low (bear)", getv(wbv, "FOOTBALL_FIELD", f"B{F + 3}"),
             sc["bear"]),
            ("DCF high (bull)", getv(wbv, "FOOTBALL_FIELD", f"C{F + 3}"),
             sc["bull"]),
        ], fmt="{:,.4f}")


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------

LABELS = {"dcf": "DCF", "statements": "three-statement",
          "lbo": "LBO", "ipo": "IPO"}


def audit(path, spec_path, model_type):
    a = Audit(f"Financopedia model audit — {LABELS.get(model_type, model_type)}")
    import json
    with open(spec_path, "r", encoding="utf-8") as fh:
        spec = json.load(fh)

    validators = {"dcf": lambda s: core.validate_spec(s)}
    try:
        import stmt_core
        validators["statements"] = stmt_core.validate
    except ImportError:
        pass
    try:
        import lbo_core
        validators["lbo"] = lbo_core.validate
    except ImportError:
        pass
    try:
        import ipo_core
        validators["ipo"] = ipo_core.validate
    except ImportError:
        pass

    try:
        validators[model_type](spec)
        a.check("Spec validates (horizon, sources, basis)", True,
                f"{core.n_hist(spec)} years of sourced history")
    except core.SpecError as e:
        a.check("Spec validates (horizon, sources, basis)", False, str(e))
        return a

    if model_type == "dcf":
        return audit_dcf(a, path, spec)

    auditors = {}
    try:
        import audit_types
        auditors = audit_types.AUDITORS
    except ImportError:
        pass
    if model_type in auditors:
        return auditors[model_type](a, path, spec)

    a.check(f"Auditor for --type {model_type} installed", False,
            "no auditor module found")
    return a


def main():
    ap = argparse.ArgumentParser(description="Audit a Financopedia workbook")
    ap.add_argument("workbook")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--type", default="dcf",
                    choices=["dcf", "statements", "lbo", "ipo"])
    args = ap.parse_args()
    return audit(args.workbook, args.spec, args.type).report()


if __name__ == "__main__":
    sys.exit(main())
