"""Auditors for the statements, LBO and IPO workbooks.

Same contract as the DCF auditor: recalculate the real workbook, then compare
it line by line against an independently written Python engine.
"""

from __future__ import annotations

import shutil

import dcf_core as core
from audit_lib import (close, compare, formula_cells_only, getv,
                       no_error_values, open_pair, workbook_checks_tab)
from xl_style import col


def _tabs(a, wb_f, needed):
    missing = [s for s in needed if s not in wb_f.sheetnames]
    return a.check("All required tabs present", not missing,
                   f"missing: {missing}" if missing else "/".join(needed))


def _hist_values(a, ws, spec, rows, keys):
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
                   else f"{len(keys)} line items x {nh} years")


def _sourced(a, ws, rows, src_col, keys):
    missing = [k for k in keys
               if not str(ws.cell(row=rows[k], column=src_col).value or "").strip()]
    return a.check("Every historical line carries a filing source", not missing,
                   f"missing: {missing}" if missing
                   else f"{len(keys)}/{len(keys)} lines sourced")


def _basis(a, ws, spec, scalar_addr, vector_rows, bcol, presentation=frozenset()):
    missing = [k for k, addr in scalar_addr.items()
               if k not in presentation
               and not str(ws.cell(row=int(addr[1:]), column=bcol).value or "").strip()]
    missing += [k for k, r in vector_rows.items()
                if not str(ws.cell(row=r, column=bcol).value or "").strip()]
    return a.check("Every assumption states its basis", not missing,
                   f"missing: {missing}" if missing else "all assumptions annotated")


def _all_formulas(a, ws, addrs, name, detail):
    gaps = [ad for ad in addrs
            if not str(ws[ad].value or "").startswith("=")]
    return a.check(name, not gaps, f"{len(gaps)} non-formula: {gaps[:5]}" if gaps
                   else detail)


# --------------------------------------------------------------------------
# three-statement
# --------------------------------------------------------------------------


def audit_statements(a, path, spec):
    import stmt_core as st
    from build_statements import STMT

    expected = st.run(spec)
    nh, nf = core.n_hist(spec), core.n_fcst(spec)
    H, B, N, C, I, R = (STMT["HISTORICALS"], STMT["BALANCE"], STMT["INCOME"],
                        STMT["CASHFLOW"], STMT["INPUTS"], STMT["RATIOS"])

    wb_f, wbv, tmp = open_pair(path)
    a.check("Workbook recalculates in LibreOffice", True, "headless round-trip")
    _tabs(a, wb_f, ["README", "INPUTS", "HISTORICALS", "INCOME", "BALANCE",
                    "CASHFLOW", "RATIOS", "CHECKS"])
    a.info("Horizons", f"{nh} historical years, {nf} forecast years")

    formula_cells_only(a, wb_f, ["INCOME", "BALANCE", "CASHFLOW", "RATIOS"])

    _all_formulas(a, wb_f["INCOME"],
                  [f"{col(2 + t)}{N[k]}" for t in range(nf) for k in N],
                  "Income statement is 100% formulas", f"{nf * len(N)} cells")
    _all_formulas(a, wb_f["BALANCE"],
                  [f"{col(2 + t)}{B[k]}" for t in range(nf) for k in B],
                  "Balance sheet is 100% formulas", f"{nf * len(B)} cells")
    _all_formulas(a, wb_f["CASHFLOW"],
                  [f"{col(2 + t)}{C[k]}" for t in range(nf) for k in C],
                  "Cash flow statement is 100% formulas", f"{nf * len(C)} cells")

    hkeys = st.HIST_IS + st.HIST_ASSETS + st.HIST_LIABS
    _hist_values(a, wb_f["HISTORICALS"], spec, H, hkeys)
    _sourced(a, wb_f["HISTORICALS"], H, 2 + nh, hkeys)

    ws = wb_f["INPUTS"]
    bad = []
    for key in st.SCALARS:
        got, want = ws[I[key]].value, spec["inputs"][key]
        if not isinstance(got, (int, float)) or not close(float(got), float(want)):
            bad.append(f"{key}: sheet={got} spec={want}")
    for key in st.VECTORS:
        for t in range(nf):
            got = ws[f"{col(2 + t)}{I[key]}"].value
            want = spec["inputs"][key][t]
            if not isinstance(got, (int, float)) or not close(float(got), float(want)):
                bad.append(f"{key}[{t}]")
    a.check("INPUTS match the spec exactly", not bad, "; ".join(bad[:4]) if bad
            else f"{len(st.SCALARS)} scalars + {len(st.VECTORS) * nf} driver cells")

    _basis(a, ws, spec, {k: I[k] for k in st.SCALARS},
           {k: I[k] for k in st.VECTORS}, max(2 + nf, 5))
    a.info("Estimated inputs (amber in the workbook)",
           ", ".join(spec["inputs"].get("estimates", [])) or "none declared")

    no_error_values(a, wbv)

    # ---- the line-by-line comparison ------------------------------------
    def row_pairs(sheet, rowmap, key, series, fmt="{:,.1f}"):
        return [(f"Y{t+1}", getv(wbv, sheet, f"{col(2 + t)}{rowmap[key]}"),
                 series[t]) for t in range(nf)]

    compare(a, "Income statement matches the Python engine",
            [("revenue Y1", getv(wbv, "INCOME", f"B{N['revenue']}"), expected.revenue[0]),
             (f"revenue Y{nf}", getv(wbv, "INCOME", f"{col(1 + nf)}{N['revenue']}"),
              expected.revenue[-1]),
             ("EBITDA Y1", getv(wbv, "INCOME", f"B{N['ebitda']}"), expected.ebitda[0]),
             ("interest Y1", getv(wbv, "INCOME", f"B{N['interest_expense']}"),
              expected.interest_expense[0]),
             ("tax Y1", getv(wbv, "INCOME", f"B{N['tax']}"), expected.tax[0]),
             ("net income Y1", getv(wbv, "INCOME", f"B{N['net_income']}"),
              expected.net_income[0]),
             (f"net income Y{nf}",
              getv(wbv, "INCOME", f"{col(1 + nf)}{N['net_income']}"),
              expected.net_income[-1])])

    compare(a, "Net income matches year by year",
            row_pairs("INCOME", N, "net_income", expected.net_income))
    compare(a, "Closing cash matches year by year",
            row_pairs("CASHFLOW", C, "closing_cash", expected.cash))
    compare(a, "Total assets match year by year",
            row_pairs("BALANCE", B, "total_assets", expected.total_assets))
    compare(a, "Shareholders' equity matches year by year",
            row_pairs("BALANCE", B, "equity", expected.equity))
    compare(a, "Term debt matches year by year",
            row_pairs("BALANCE", B, "debt", expected.debt))
    compare(a, "Cash from operations matches year by year",
            row_pairs("CASHFLOW", C, "cfo", expected.cfo))

    # ---- the identity that matters --------------------------------------
    diffs = [getv(wbv, "BALANCE", f"{col(2 + t)}{B['balance']}") for t in range(nf)]
    worst = max((abs(d) for d in diffs if d is not None), default=None)
    a.check("Balance sheet balances in every forecast year",
            worst is not None and worst < 0.01,
            f"worst imbalance {worst:,.6f} across {nf} years" if worst is not None
            else "balance row produced no values")

    hdiffs = [getv(wbv, "HISTORICALS", f"{col(2 + t)}{H['balance']}")
              for t in range(nh)]
    hworst = max((abs(d) for d in hdiffs if d is not None), default=None)
    a.check("Reported balance sheet balanced in every year",
            hworst is not None and hworst < 0.01,
            f"worst imbalance {hworst:,.6f} across {nh} years"
            if hworst is not None else "no values")

    cash_vals = [getv(wbv, "BALANCE", f"{col(2 + t)}{B['cash']}") for t in range(nf)]
    cash_vals = [c for c in cash_vals if c is not None]
    a.check("Cash never falls below the minimum",
            cash_vals and min(cash_vals) >= spec["inputs"]["min_cash"] - 0.01,
            f"minimum cash {min(cash_vals):,.1f} vs floor "
            f"{spec['inputs']['min_cash']:,.1f}" if cash_vals else "no values")

    # ---- DuPont ---------------------------------------------------------
    from build_statements import DUP
    d = st.dupont(spec, expected)
    _tabs(a, wb_f, ["DUPONT"])
    compare(a, "DuPont components match the Python engine", [
        ("net margin Y1", getv(wbv, "DUPONT", f"{col(2 + nh)}{DUP['net_margin']}"),
         d["net_margin"][0]),
        ("asset turnover Y1",
         getv(wbv, "DUPONT", f"{col(2 + nh)}{DUP['asset_turnover']}"),
         d["asset_turnover"][0]),
        ("equity multiplier Y1",
         getv(wbv, "DUPONT", f"{col(2 + nh)}{DUP['equity_multiplier']}"),
         d["equity_multiplier"][0]),
        ("ROE Y1", getv(wbv, "DUPONT", f"{col(2 + nh)}{DUP['roe']}"), d["roe"][0]),
        (f"ROE Y{nf}",
         getv(wbv, "DUPONT", f"{col(1 + nh + nf)}{DUP['roe']}"), d["roe"][-1]),
    ], fmt="{:,.6f}")

    drift = [getv(wbv, "DUPONT", f"{col(2 + nh + t)}{DUP['roe_check']}")
             for t in range(nf)]
    worst_d = max((abs(x) for x in drift if x is not None), default=None)
    a.check("DuPont decomposition is an exact identity",
            worst_d is not None and worst_d < 1e-9,
            f"worst drift {worst_d:.2e} — margin x turnover x leverage equals "
            "ROE computed directly" if worst_d is not None else "no values")

    ratios = st.ratios(spec, expected)
    compare(a, "Ratios tab matches the computed statements",
            [("EBITDA margin Y1",
              getv(wbv, "RATIOS", f"{col(2 + nh)}{R['ebitda_margin']}"),
              ratios["ebitda_margin"][0]),
             ("net debt/EBITDA Y1",
              getv(wbv, "RATIOS", f"{col(2 + nh)}{R['net_debt_ebitda']}"),
              ratios["net_debt_ebitda"][0]),
             ("ROE Y1", getv(wbv, "RATIOS", f"{col(2 + nh)}{R['roe']}"),
              d["roe_direct"][0]),
             ("ROCE Y1", getv(wbv, "RATIOS", f"{col(2 + nh)}{R['roce']}"),
              ratios["roce"][0]),
             ("sustainable growth Y1",
              getv(wbv, "RATIOS", f"{col(2 + nh)}{R['sustainable_growth']}"),
              ratios["sustainable_growth"][0]),
             ("CFO/revenue Y1",
              getv(wbv, "RATIOS", f"{col(2 + nh)}{R['cfo_sales']}"),
              ratios["cfo_sales"][0]),
             ("interest cover Y1",
              getv(wbv, "RATIOS", f"{col(2 + nh)}{R['interest_cover']}"),
              ratios["interest_cover"][0])], fmt="{:,.4f}")

    workbook_checks_tab(a, wbv)
    shutil.rmtree(tmp, ignore_errors=True)
    return a


# --------------------------------------------------------------------------
# LBO
# --------------------------------------------------------------------------


def audit_lbo(a, path, spec):
    import lbo_core as lbo
    from build_lbo import GRID, LBOC, RET, debt_rows, su_rows

    expected = lbo.run(spec)
    nh, nf = core.n_hist(spec), core.n_fcst(spec)
    nt = len(spec["debt_tranches"])
    I, H, P = LBOC["INPUTS"], LBOC["HISTORICALS"], LBOC["PROJECTION"]
    S, DR, SG = su_rows(nt), debt_rows(nt), LBOC["SENSITIVITY"]

    wb_f, wbv, tmp = open_pair(path)
    a.check("Workbook recalculates in LibreOffice", True, "headless round-trip")
    _tabs(a, wb_f, ["README", "INPUTS", "HISTORICALS", "SOURCES_USES",
                    "PROJECTION", "DEBT", "RETURNS", "SENSITIVITY", "CHECKS"])
    a.info("Structure", f"{nh} historical years, {nf}-year hold, "
                        f"{nt} debt tranches")

    formula_cells_only(a, wb_f, ["SOURCES_USES", "PROJECTION", "DEBT",
                                 "RETURNS", "SENSITIVITY"])

    _all_formulas(a, wb_f["PROJECTION"],
                  [f"{col(2 + t)}{P[k]}" for t in range(nf) for k in P],
                  "Projection is 100% formulas", f"{nf * len(P)} cells")
    debt_addrs = [f"{col(2 + t)}{b[k]}" for t in range(nf)
                  for b in DR["blocks"]
                  for k in ("opening", "mandatory", "sweep", "closing", "interest")]
    _all_formulas(a, wb_f["DEBT"], debt_addrs,
                  "Debt schedule is 100% formulas", f"{len(debt_addrs)} cells")

    hkeys = ["revenue", "ebitda", "capex", "nwc_balance"]
    _hist_values(a, wb_f["HISTORICALS"], spec, H, hkeys)
    _sourced(a, wb_f["HISTORICALS"], H, 2 + nh, hkeys)

    ws = wb_f["INPUTS"]
    bad = []
    for key in lbo.SCALARS:
        got, want = ws[I[key]].value, spec["inputs"][key]
        if not isinstance(got, (int, float)) or not close(float(got), float(want)):
            bad.append(f"{key}: sheet={got} spec={want}")
    for key in lbo.VECTORS:
        for t in range(nf):
            got = ws[f"{col(2 + t)}{I[key]}"].value
            want = spec["inputs"][key][t]
            if not isinstance(got, (int, float)) or not close(float(got), float(want)):
                bad.append(f"{key}[{t}]")
    for k, tr in enumerate(spec["debt_tranches"]):
        r = I["tranche_start"] + k
        for cl, key in (("B", "turns"), ("C", "rate"), ("D", "amort_pct")):
            got = ws[f"{cl}{r}"].value
            if not isinstance(got, (int, float)) or not close(float(got),
                                                              float(tr[key])):
                bad.append(f"tranche {k} {key}")
    a.check("INPUTS and tranche terms match the spec", not bad,
            "; ".join(bad[:4]) if bad
            else f"{len(lbo.SCALARS)} scalars, {len(lbo.VECTORS) * nf} drivers, "
                 f"{nt} tranches")

    _basis(a, ws, spec, {k: I[k] for k in lbo.SCALARS},
           {k: I[k] for k in lbo.VECTORS}, max(2 + nf, 5), lbo.PRESENTATION)
    missing_tr = [k for k in range(nt)
                  if not str(ws.cell(row=I["tranche_start"] + k,
                                     column=6).value or "").strip()]
    a.check("Every debt tranche states its basis", not missing_tr,
            f"missing: {missing_tr}" if missing_tr
            else f"{nt}/{nt} tranches sourced")
    a.info("Estimated inputs (amber in the workbook)",
           ", ".join(spec["inputs"].get("estimates", [])) or "none declared")

    no_error_values(a, wbv)

    compare(a, "Sources and uses match the Python engine", [
        ("LTM EBITDA", getv(wbv, "SOURCES_USES", f"B{S['ltm_ebitda']}"),
         expected.ltm_ebitda),
        ("entry EV", getv(wbv, "SOURCES_USES", f"B{S['entry_ev']}"),
         expected.entry_ev),
        ("total debt", getv(wbv, "SOURCES_USES", f"B{S['total_debt']}"),
         expected.total_debt),
        ("sponsor equity", getv(wbv, "SOURCES_USES", f"B{S['sponsor']}"),
         expected.sponsor_equity),
        ("total uses", getv(wbv, "SOURCES_USES", f"B{S['total_uses']}"),
         expected.total_uses),
        ("entry net debt", getv(wbv, "SOURCES_USES", f"B{S['entry_net_debt']}"),
         expected.entry_net_debt),
    ], fmt="{:,.1f}")

    su_check = getv(wbv, "SOURCES_USES", f"B{S['check']}")
    a.check("Sources equal uses", su_check is not None and abs(su_check) < 0.01,
            f"difference {su_check:,.6f}" if su_check is not None else "no value")

    compare(a, "Debt balances match year by year",
            [(f"Y{t+1}", getv(wbv, "DEBT", f"{col(2 + t)}{DR['total_closing']}"),
              expected.total_closing_debt[t]) for t in range(nf)], fmt="{:,.1f}")
    compare(a, "Closing cash matches year by year",
            [(f"Y{t+1}", getv(wbv, "DEBT", f"{col(2 + t)}{DR['closing_cash']}"),
              expected.closing_cash[t]) for t in range(nf)], fmt="{:,.1f}")
    compare(a, "Free cash flow matches year by year",
            [(f"Y{t+1}", getv(wbv, "PROJECTION", f"{col(2 + t)}{P['fcf']}"),
              expected.fcf[t]) for t in range(nf)], fmt="{:,.1f}")
    compare(a, "Interest expense matches year by year",
            [(f"Y{t+1}", getv(wbv, "PROJECTION", f"{col(2 + t)}{P['interest']}"),
              expected.interest[t]) for t in range(nf)], fmt="{:,.1f}")

    compare(a, "Returns match the Python engine", [
        ("exit EV", getv(wbv, "RETURNS", f"B{RET['exit_ev']}"), expected.exit_ev),
        ("exit net debt", getv(wbv, "RETURNS", f"B{RET['exit_net_debt']}"),
         expected.exit_net_debt),
        ("exit equity", getv(wbv, "RETURNS", f"B{RET['exit_equity']}"),
         expected.exit_equity),
        ("money multiple", getv(wbv, "RETURNS", f"B{RET['money_multiple']}"),
         expected.money_multiple),
        ("IRR", getv(wbv, "RETURNS", f"B{RET['irr']}"), expected.irr),
    ], fmt="{:,.4f}")

    compare(a, "Value attribution matches the Python engine", [
        ("EBITDA growth", getv(wbv, "RETURNS", f"B{RET['attr_ebitda']}"),
         expected.attr_ebitda_growth),
        ("multiple change", getv(wbv, "RETURNS", f"B{RET['attr_multiple']}"),
         expected.attr_multiple),
        ("debt paydown", getv(wbv, "RETURNS", f"B{RET['attr_debt']}"),
         expected.attr_debt_paydown),
        ("total", getv(wbv, "RETURNS", f"B{RET['attr_total']}"),
         expected.attr_total),
    ], fmt="{:,.1f}")

    attr_check = getv(wbv, "RETURNS", f"B{RET['attr_check']}")
    a.check("Attribution is an exact identity",
            attr_check is not None and abs(attr_check) < 0.01,
            f"residual {attr_check:,.6f} — the three components sum exactly to "
            "the change in equity value" if attr_check is not None else "no value")

    cc = col(SG["grid_first_col"] + GRID // 2)
    centre = getv(wbv, "SENSITIVITY", f"{cc}{SG['y_start'] + GRID // 2}")
    a.check("Sensitivity centre equals the headline IRR",
            close(centre, expected.irr, 1e-4),
            f"grid centre {centre:.4%} vs base {expected.irr:.4%}"
            if centre is not None else "grid centre is blank")

    cells = [getv(wbv, "SENSITIVITY", f"{col(SG['grid_first_col'] + k)}"
                  f"{SG['y_start'] + j}") for k in range(GRID) for j in range(GRID)]
    cells = [c for c in cells if c is not None]
    a.check("Sensitivity grid actually varies",
            len({round(c, 8) for c in cells}) > 1,
            f"{len(cells)} live cells, IRR range {min(cells):.1%}–{max(cells):.1%}"
            if cells else "grid produced no values")

    # independent recomputation of a corner, not just the centre
    corner = getv(wbv, "SENSITIVITY", f"{col(SG['grid_first_col'])}{SG['y_start']}")
    want = lbo.irr_at(spec,
                      spec["inputs"]["entry_multiple"] - 2 * spec["inputs"]["entry_step"],
                      spec["inputs"]["exit_multiple"] - 2 * spec["inputs"]["exit_step"],
                      expected)
    a.check("Sensitivity corner recomputes correctly", close(corner, want, 1e-6),
            f"corner {corner:.4%} vs independent {want:.4%}"
            if corner is not None else "corner is blank")

    workbook_checks_tab(a, wbv)
    shutil.rmtree(tmp, ignore_errors=True)
    return a


# --------------------------------------------------------------------------
# IPO
# --------------------------------------------------------------------------


def audit_ipo(a, path, spec):
    import ipo_core as ipo
    from build_ipo import GRID, IPOC, proceeds_rows

    expected = ipo.run(spec)
    nh, nf = core.n_hist(spec), core.n_fcst(spec)
    nu = len(spec.get("use_of_proceeds", []))
    I, H, V, O = (IPOC["INPUTS"], IPOC["HISTORICALS"], IPOC["VALUATION"],
                  IPOC["OFFERING"])
    P, S = proceeds_rows(nu), IPOC["SENSITIVITY"]

    wb_f, wbv, tmp = open_pair(path)
    a.check("Workbook recalculates in LibreOffice", True, "headless round-trip")
    _tabs(a, wb_f, ["README", "INPUTS", "HISTORICALS", "VALUATION", "OFFERING",
                    "PROCEEDS", "SENSITIVITY", "CHECKS"])
    a.info("Structure", f"{nh} historical years, {len(spec['comps'])} peers, "
                        f"{nu} stated uses of proceeds")

    formula_cells_only(a, wb_f, ["VALUATION", "OFFERING", "SENSITIVITY"])

    _all_formulas(a, wb_f["VALUATION"], [f"B{V[k]}" for k in V],
                  "Valuation build-up is 100% formulas", f"{len(V)} cells")
    _all_formulas(a, wb_f["OFFERING"], [f"B{O[k]}" for k in O],
                  "Offering build-up is 100% formulas", f"{len(O)} cells")

    hkeys = ["revenue", "ebitda", "net_income"]
    _hist_values(a, wb_f["HISTORICALS"], spec, H, hkeys)
    _sourced(a, wb_f["HISTORICALS"], H, 2 + nh, hkeys)

    ws = wb_f["INPUTS"]
    bad = []
    for key in ipo.SCALARS:
        got, want = ws[I[key]].value, spec["inputs"][key]
        if not isinstance(got, (int, float)) or not close(float(got), float(want)):
            bad.append(f"{key}: sheet={got} spec={want}")
    for key in ipo.VECTORS:
        for t in range(nf):
            got = ws[f"{col(2 + t)}{I[key]}"].value
            want = spec["inputs"][key][t]
            if not isinstance(got, (int, float)) or not close(float(got), float(want)):
                bad.append(f"{key}[{t}]")
    for k, c in enumerate(spec["comps"]):
        r = I["comps_start"] + k
        for cl, key in (("B", "ev_ebitda"), ("C", "ev_sales"), ("D", "pe")):
            got = ws[f"{cl}{r}"].value
            if not isinstance(got, (int, float)) or not close(float(got),
                                                              float(c[key])):
                bad.append(f"peer {k} {key}")
    a.check("INPUTS and peer multiples match the spec", not bad,
            "; ".join(bad[:4]) if bad
            else f"{len(ipo.SCALARS)} scalars, {len(ipo.VECTORS) * nf} drivers, "
                 f"{len(spec['comps'])} peers")

    _basis(a, ws, spec, {k: I[k] for k in ipo.SCALARS},
           {k: I[k] for k in ipo.VECTORS}, max(2 + nf, 5), ipo.PRESENTATION)
    missing_pe = [k for k in range(len(spec["comps"]))
                  if not str(ws.cell(row=I["comps_start"] + k,
                                     column=5).value or "").strip()]
    a.check("Every peer multiple carries a source", not missing_pe,
            f"missing: {missing_pe}" if missing_pe
            else f"{len(spec['comps'])}/{len(spec['comps'])} peers sourced")
    a.info("Estimated inputs (amber in the workbook)",
           ", ".join(spec["inputs"].get("estimates", [])) or "none declared")

    no_error_values(a, wbv)

    compare(a, "Valuation build-up matches the Python engine", [
        ("NTM revenue", getv(wbv, "VALUATION", f"B{V['ntm_revenue']}"),
         expected.ntm_revenue),
        ("NTM EBITDA", getv(wbv, "VALUATION", f"B{V['ntm_ebitda']}"),
         expected.ntm_ebitda),
        ("peer EV/EBITDA", getv(wbv, "VALUATION", f"B{V['peer_ev_ebitda']}"),
         expected.peer_ev_ebitda),
        ("EV/EBITDA equity", getv(wbv, "VALUATION", f"B{V['equity_ev_ebitda']}"),
         expected.equity_ev_ebitda),
        ("EV/Sales equity", getv(wbv, "VALUATION", f"B{V['equity_ev_sales']}"),
         expected.equity_ev_sales),
        ("P/E equity", getv(wbv, "VALUATION", f"B{V['equity_pe']}"),
         expected.equity_pe),
        ("blended", getv(wbv, "VALUATION", f"B{V['blended']}"),
         expected.blended_equity),
        ("pre-money", getv(wbv, "VALUATION", f"B{V['pre_money']}"),
         expected.pre_money),
    ], fmt="{:,.2f}")

    compare(a, "Offering structure matches the Python engine", [
        ("offer price", getv(wbv, "OFFERING", f"B{O['offer_price']}"),
         expected.offer_price),
        ("primary shares", getv(wbv, "OFFERING", f"B{O['primary_shares']}"),
         expected.primary_shares),
        ("post-IPO shares", getv(wbv, "OFFERING", f"B{O['post_shares']}"),
         expected.post_shares),
        ("post-money", getv(wbv, "OFFERING", f"B{O['post_money']}"),
         expected.post_money),
        ("free float", getv(wbv, "OFFERING", f"B{O['free_float']}"),
         expected.free_float),
        ("dilution", getv(wbv, "OFFERING", f"B{O['dilution']}"),
         expected.dilution),
        ("implied EV/EBITDA", getv(wbv, "OFFERING", f"B{O['implied_ev_ebitda']}"),
         expected.implied_ev_ebitda),
    ], fmt="{:,.4f}")

    compare(a, "Proceeds match the Python engine", [
        ("gross primary", getv(wbv, "PROCEEDS", f"B{P['gross_primary']}"),
         expected.gross_primary),
        ("gross secondary", getv(wbv, "PROCEEDS", f"B{P['gross_secondary']}"),
         expected.gross_secondary),
        ("underwriting fees", getv(wbv, "PROCEEDS", f"B{P['underwriting_fees']}"),
         expected.underwriting_fees),
        ("net primary", getv(wbv, "PROCEEDS", f"B{P['net_primary']}"),
         expected.net_primary),
        ("greenshoe proceeds",
         getv(wbv, "PROCEEDS", f"B{P['greenshoe_proceeds']}"),
         expected.greenshoe_proceeds),
    ], fmt="{:,.2f}")

    # the identity that proves the share solve is right
    post_money = getv(wbv, "OFFERING", f"B{O['post_money']}")
    post_shares = getv(wbv, "OFFERING", f"B{O['post_shares']}")
    price = getv(wbv, "OFFERING", f"B{O['offer_price']}")
    ok = (post_money is not None and post_shares
          and close(post_money / post_shares, price, 1e-9))
    a.check("Post-money value per share equals the offer price", ok,
            f"{post_money / post_shares:,.6f} vs {price:,.6f}"
            if ok or (post_money and post_shares) else "missing values")

    gap = getv(wbv, "PROCEEDS", f"B{P['uses_check']}")
    a.check("Use of proceeds reconciles to net primary",
            gap is not None and abs(gap) < 0.01,
            f"unallocated {gap:,.2f} — report it rather than inventing a use"
            if gap is not None else "no value")

    cc = col(S["grid_first_col"] + GRID // 2)
    centre = getv(wbv, "SENSITIVITY", f"{cc}{S['y_start'] + GRID // 2}")
    a.check("Sensitivity centre equals the offer price",
            close(centre, expected.offer_price, 1e-6),
            f"grid centre {centre:,.4f} vs offer {expected.offer_price:,.4f}"
            if centre is not None else "grid centre is blank")

    corner = getv(wbv, "SENSITIVITY", f"{col(S['grid_first_col'])}{S['y_start']}")
    want = ipo.offer_price_at(
        spec,
        expected.peer_ev_ebitda - 2 * spec["inputs"]["multiple_step"],
        spec["inputs"]["ipo_discount"] - 2 * spec["inputs"]["discount_step"],
        expected)
    a.check("Sensitivity corner recomputes correctly", close(corner, want, 1e-6),
            f"corner {corner:,.4f} vs independent {want:,.4f}"
            if corner is not None else "corner is blank")

    cells = [getv(wbv, "SENSITIVITY", f"{col(S['grid_first_col'] + k)}"
                  f"{S['y_start'] + j}") for k in range(GRID) for j in range(GRID)]
    cells = [c for c in cells if c is not None]
    a.check("Sensitivity grid actually varies",
            len({round(c, 8) for c in cells}) > 1,
            f"{len(cells)} live cells, price range {min(cells):,.2f}–"
            f"{max(cells):,.2f}" if cells else "grid produced no values")

    workbook_checks_tab(a, wbv)
    shutil.rmtree(tmp, ignore_errors=True)
    return a


AUDITORS = {"statements": audit_statements, "lbo": audit_lbo, "ipo": audit_ipo}
