#!/usr/bin/env python3
"""IPO workbook: peer-based pricing, offer structure, dilution, use of proceeds."""

from __future__ import annotations

from openpyxl import Workbook

import dcf_core as core
import ipo_core as ipo
from xl_style import (CUR, F_ESTIMATE, F_INPUT, F_NOTE, F_SUB, F_TITLE,
                      FILL_BAND, FILL_EST, FILL_OUT, MULT, NUM, PCT,
                      checks_sheet, col, head, label, note, put, readme_sheet,
                      widths, year_widths)

GRID = 5

IPOC = {
    "INPUTS": {
        "ipo_discount": "B4", "primary_proceeds_target": "B5",
        "secondary_shares": "B6", "pre_ipo_shares": "B7",
        "underwriting_fee_pct": "B8", "other_offering_costs": "B9",
        "greenshoe_pct": "B10", "net_debt": "B11", "price_range_pct": "B12",
        "weight_ev_ebitda": "B13", "weight_ev_sales": "B14", "weight_pe": "B15",
        "multiple_step": "B16", "discount_step": "B17",
        "rev_growth": 20, "ebitda_margin": 21, "net_margin": 22,
        "comps_start": 25,
    },
    "HISTORICALS": {
        "revenue": 4, "ebitda": 5, "net_income": 6, "margin": 7,
        "cagr": 10, "margin_avg": 11,
    },
    "VALUATION": {
        "ntm_revenue": 4, "ntm_ebitda": 5, "ntm_net_income": 6,
        "peer_ev_ebitda": 8, "peer_ev_sales": 9, "peer_pe": 10,
        "equity_ev_ebitda": 12, "equity_ev_sales": 13, "equity_pe": 14,
        "blended": 16, "discount": 17, "pre_money": 18,
    },
    "OFFERING": {
        "offer_price": 4, "price_low": 5, "price_high": 6,
        "pre_ipo_shares": 8, "primary_shares": 9, "secondary_shares": 10,
        "base_offered": 11, "greenshoe_shares": 12, "post_shares": 13,
        "pre_money": 15, "post_money": 16, "free_float": 17,
        "free_float_shoe": 18, "dilution": 19,
        "post_net_debt": 21, "post_ev": 22, "implied_ev_ebitda": 23,
        "implied_pe": 24, "discount_to_peers": 25,
    },
    "PROCEEDS": {
        "gross_primary": 4, "gross_secondary": 5, "total_gross": 6,
        "underwriting_fees": 7, "other_costs": 8, "net_primary": 9,
        "net_secondary": 10, "greenshoe_proceeds": 11,
        "uses_header": 13, "uses_first": 14,
    },
    "SENSITIVITY": {"x_row": 4, "y_start": 5, "grid_first_col": 3},
}


def proceeds_rows(nu):
    r = dict(IPOC["PROCEEDS"])
    r["uses_total"] = r["uses_first"] + max(nu, 1)
    r["uses_check"] = r["uses_total"] + 1
    return r


def build_inputs(wb, spec):
    ws = wb.create_sheet("INPUTS")
    i = spec["inputs"]
    basis, est = i.get("basis", {}), set(i.get("estimates", []))
    nf = core.n_fcst(spec)
    bcol = max(2 + nf, 5)
    I = IPOC["INPUTS"]
    units = spec["meta"]["units"]

    ws["A1"] = "INPUTS — offering terms, peer set and the valuation blend"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("The IPO discount is the most judgemental number here, which is "
                "why it is an axis of the sensitivity grid.")
    ws["A2"].font = F_NOTE
    head(ws, 3, ["Assumption", "Value", "Unit"])
    ws.cell(row=3, column=bcol, value="Basis / source").font = F_SUB

    scalars = [
        ("ipo_discount", "IPO discount to peers", PCT, "%"),
        ("primary_proceeds_target", "Primary gross proceeds target", NUM, units),
        ("secondary_shares", "Secondary shares sold", NUM, "shares"),
        ("pre_ipo_shares", "Pre-IPO shares outstanding", NUM, "shares"),
        ("underwriting_fee_pct", "Underwriting fee", PCT, "%"),
        ("other_offering_costs", "Other offering costs", NUM, units),
        ("greenshoe_pct", "Greenshoe (% of base offer)", PCT, "%"),
        ("net_debt", "Net debt before the offering", NUM, units),
        ("price_range_pct", "Marketing range (+/-)", PCT, "%"),
        ("weight_ev_ebitda", "Weight: EV/EBITDA method", PCT, "%"),
        ("weight_ev_sales", "Weight: EV/Sales method", PCT, "%"),
        ("weight_pe", "Weight: P/E method", PCT, "%"),
        ("multiple_step", "Sensitivity: peer multiple step", MULT, "x"),
        ("discount_step", "Sensitivity: IPO discount step", PCT, "%"),
    ]
    for key, lab, fmt, unit in scalars:
        r = int(I[key][1:])
        label(ws, r, lab)
        is_est = key in est
        put(ws, I[key], i[key], font=F_ESTIMATE if is_est else F_INPUT, fmt=fmt,
            fill=FILL_EST if is_est else None)
        ws.cell(row=r, column=3, value=unit)
        note(ws, r, bcol, basis.get(key, ""))

    head(ws, 19, ["Forecast driver"] + [f"Y{k+1}" for k in range(nf)])
    ws.cell(row=19, column=bcol, value="Basis / source").font = F_SUB
    for key, lab in [("rev_growth", "Revenue growth"),
                     ("ebitda_margin", "EBITDA margin"),
                     ("net_margin", "Net margin")]:
        r = I[key]
        label(ws, r, lab)
        is_est = key in est
        for t in range(nf):
            put(ws, f"{col(2 + t)}{r}", i[key][t],
                font=F_ESTIMATE if is_est else F_INPUT, fmt=PCT,
                fill=FILL_EST if is_est else None)
        note(ws, r, bcol, basis.get(key, ""))

    head(ws, 24, ["Peer", "EV/EBITDA", "EV/Sales", "P/E"])
    ws.cell(row=24, column=5, value="Source").font = F_SUB
    for k, c in enumerate(spec["comps"]):
        r = I["comps_start"] + k
        label(ws, r, c["name"])
        put(ws, f"B{r}", c["ev_ebitda"], font=F_INPUT, fmt=MULT)
        put(ws, f"C{r}", c["ev_sales"], font=F_INPUT, fmt=MULT)
        put(ws, f"D{r}", c["pe"], font=F_INPUT, fmt=MULT)
        note(ws, r, 5, c.get("source", ""))

    year_widths(ws, nf, label_w=38, year_w=12)
    widths(ws, {"C": 13, "D": 13, "E": 48, col(bcol): 56})
    return ws


def build_historicals(wb, spec):
    ws = wb.create_sheet("HISTORICALS")
    h, src = spec["historicals"], spec["historicals"].get("sources", {})
    nh = core.n_hist(spec)
    scol, last = 2 + nh, col(1 + nh)
    H = IPOC["HISTORICALS"]

    ws["A1"] = f"HISTORICALS — {nh} reported years"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("A long record is what distinguishes a pricing argument from a "
                "pitch; the last year drives the NTM figures the offer is priced on.")
    ws["A2"].font = F_NOTE
    head(ws, 3, ["Metric"] + [str(y) for y in h["years"]])
    ws.cell(row=3, column=scol, value="Source (filing, date)").font = F_SUB

    for key, lab in [("revenue", "Revenue"), ("ebitda", "EBITDA"),
                     ("net_income", "Net income")]:
        r = H[key]
        label(ws, r, lab)
        for t in range(nh):
            put(ws, f"{col(2 + t)}{r}", h[key][t], font=F_INPUT, fmt=NUM)
        note(ws, r, scol, src.get(key, ""))

    label(ws, H["margin"], "EBITDA margin")
    for t in range(nh):
        c = col(2 + t)
        put(ws, f"{c}{H['margin']}", f"={c}{H['ebitda']}/{c}{H['revenue']}", fmt=PCT)

    ws.cell(row=9, column=1, value=f"What {nh} years of history says").font = F_TITLE
    for r, lab, formula, why in [
        (H["cagr"], "Revenue CAGR over the period",
         f"=(({last}{H['revenue']}/B{H['revenue']})^(1/{nh - 1}))-1",
         "Investors price growth off the record, not the forecast"),
        (H["margin_avg"], "EBITDA margin — average",
         f"=AVERAGE(B{H['margin']}:{last}{H['margin']})", ""),
    ]:
        label(ws, r, lab)
        put(ws, f"B{r}", formula, fmt=PCT, fill=FILL_BAND)
        if why:
            note(ws, r, 3, why)

    year_widths(ws, nh, label_w=34, year_w=12, extra=56)
    return ws


def build_valuation(wb, spec):
    ws = wb.create_sheet("VALUATION")
    nh = core.n_hist(spec)
    HL = col(1 + nh)
    H, I, V = IPOC["HISTORICALS"], IPOC["INPUTS"], IPOC["VALUATION"]
    nc = len(spec["comps"])
    clast = I["comps_start"] + nc - 1

    ws["A1"] = "VALUATION — three peer methods, blended, then discounted"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("The blend weights are inputs, so the argument is visible rather "
                "than buried in one multiple.")
    ws["A2"].font = F_NOTE
    head(ws, 3, ["Item", "Value"])

    for r, lab, formula, fmt, fill in [
        (V["ntm_revenue"], "NTM revenue",
         f"=HISTORICALS!{HL}{H['revenue']}*(1+INPUTS!B{I['rev_growth']})", NUM, None),
        (V["ntm_ebitda"], "NTM EBITDA",
         f"=B{V['ntm_revenue']}*INPUTS!B{I['ebitda_margin']}", NUM, None),
        (V["ntm_net_income"], "NTM net income",
         f"=B{V['ntm_revenue']}*INPUTS!B{I['net_margin']}", NUM, None),
        (V["peer_ev_ebitda"], "Peer median EV/EBITDA",
         f"=MEDIAN(INPUTS!B{I['comps_start']}:B{clast})", MULT, None),
        (V["peer_ev_sales"], "Peer median EV/Sales",
         f"=MEDIAN(INPUTS!C{I['comps_start']}:C{clast})", MULT, None),
        (V["peer_pe"], "Peer median P/E",
         f"=MEDIAN(INPUTS!D{I['comps_start']}:D{clast})", MULT, None),
        (V["equity_ev_ebitda"], "Equity value — EV/EBITDA method",
         f"=B{V['peer_ev_ebitda']}*B{V['ntm_ebitda']}-INPUTS!$B$11", NUM, None),
        (V["equity_ev_sales"], "Equity value — EV/Sales method",
         f"=B{V['peer_ev_sales']}*B{V['ntm_revenue']}-INPUTS!$B$11", NUM, None),
        (V["equity_pe"], "Equity value — P/E method",
         f"=B{V['peer_pe']}*B{V['ntm_net_income']}", NUM, None),
        (V["blended"], "Blended equity value (weighted)",
         f"=INPUTS!$B$13*B{V['equity_ev_ebitda']}+INPUTS!$B$14*B{V['equity_ev_sales']}"
         f"+INPUTS!$B$15*B{V['equity_pe']}", NUM, FILL_BAND),
        (V["discount"], "Less: IPO discount", "=INPUTS!$B$4", PCT, None),
        (V["pre_money"], "Pre-money equity value",
         f"=B{V['blended']}*(1-B{V['discount']})", NUM, FILL_OUT),
    ]:
        label(ws, r, lab)
        put(ws, f"B{r}", formula, fmt=fmt, fill=fill)

    note(ws, V["equity_pe"], 3,
         "The P/E method needs no net debt adjustment — earnings are already "
         "after interest")
    widths(ws, {"A": 42, "B": 18, "C": 56})
    return ws


def build_offering(wb, spec):
    ws = wb.create_sheet("OFFERING")
    V, O, P = IPOC["VALUATION"], IPOC["OFFERING"], proceeds_rows(
        len(spec.get("use_of_proceeds", [])))

    ws["A1"] = "OFFERING — price, shares, ownership"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("Primary shares are solved from the proceeds target at the offer "
                "price, so the post-money value per share equals the offer price.")
    ws["A2"].font = F_NOTE
    head(ws, 3, ["Item", "Value"])

    for r, lab, formula, fmt, fill in [
        (O["offer_price"], "Offer price",
         f"=VALUATION!B{V['pre_money']}/INPUTS!$B$7", CUR, FILL_OUT),
        (O["price_low"], "Marketing range — low",
         f"=B{O['offer_price']}*(1-INPUTS!$B$12)", CUR, None),
        (O["price_high"], "Marketing range — high",
         f"=B{O['offer_price']}*(1+INPUTS!$B$12)", CUR, None),
        (O["pre_ipo_shares"], "Pre-IPO shares", "=INPUTS!$B$7", NUM, None),
        (O["primary_shares"], "New (primary) shares issued",
         f"=INPUTS!$B$5/B{O['offer_price']}", NUM, None),
        (O["secondary_shares"], "Secondary shares sold", "=INPUTS!$B$6", NUM, None),
        (O["base_offered"], "Base shares offered",
         f"=B{O['primary_shares']}+B{O['secondary_shares']}", NUM, None),
        (O["greenshoe_shares"], "Greenshoe shares",
         f"=B{O['base_offered']}*INPUTS!$B$10", NUM, None),
        (O["post_shares"], "Post-IPO shares outstanding",
         f"=B{O['pre_ipo_shares']}+B{O['primary_shares']}", NUM, FILL_BAND),
        (O["pre_money"], "Pre-money equity value",
         f"=VALUATION!B{V['pre_money']}", NUM, None),
        (O["post_money"], "Post-money equity value",
         f"=B{O['pre_money']}+INPUTS!$B$5", NUM, FILL_OUT),
        (O["free_float"], "Free float (base offer)",
         f"=B{O['base_offered']}/B{O['post_shares']}", PCT, None),
        (O["free_float_shoe"], "Free float (with greenshoe)",
         f"=(B{O['base_offered']}+B{O['greenshoe_shares']})/B{O['post_shares']}",
         PCT, None),
        (O["dilution"], "Dilution to existing holders",
         f"=B{O['primary_shares']}/B{O['post_shares']}", PCT, None),
        (O["post_net_debt"], "Net debt after the offering",
         f"=INPUTS!$B$11-PROCEEDS!B{P['net_primary']}", NUM, None),
        (O["post_ev"], "Post-IPO enterprise value",
         f"=B{O['post_money']}+B{O['post_net_debt']}", NUM, None),
        (O["implied_ev_ebitda"], "Implied EV/EBITDA at the offer",
         f"=B{O['post_ev']}/VALUATION!B{V['ntm_ebitda']}", MULT, FILL_BAND),
        (O["implied_pe"], "Implied P/E at the offer",
         f"=B{O['post_money']}/VALUATION!B{V['ntm_net_income']}", MULT, None),
        (O["discount_to_peers"], "Implied discount to peer EV/EBITDA",
         f"=B{O['implied_ev_ebitda']}/VALUATION!B{V['peer_ev_ebitda']}-1", PCT, None),
    ]:
        label(ws, r, lab)
        put(ws, f"B{r}", formula, fmt=fmt, fill=fill)

    note(ws, O["discount_to_peers"], 3,
         "Where the offering actually prices against the peer set, after the "
         "cash raised changes net debt")
    widths(ws, {"A": 42, "B": 18, "C": 58})
    return ws


def build_proceeds(wb, spec):
    uses = spec.get("use_of_proceeds", [])
    P = proceeds_rows(len(uses))
    O = IPOC["OFFERING"]
    ws = wb.create_sheet("PROCEEDS")

    ws["A1"] = "PROCEEDS — what is raised, what it costs, where it goes"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("Secondary proceeds go to the selling shareholders, not the "
                "company. Only net primary proceeds fund anything below.")
    ws["A2"].font = F_NOTE
    head(ws, 3, ["Item", "Amount"])

    for r, lab, formula, fill in [
        (P["gross_primary"], "Gross primary proceeds", "=INPUTS!$B$5", None),
        (P["gross_secondary"], "Gross secondary proceeds",
         f"=INPUTS!$B$6*OFFERING!B{O['offer_price']}", None),
        (P["total_gross"], "Total gross proceeds",
         f"=B{P['gross_primary']}+B{P['gross_secondary']}", FILL_BAND),
        (P["underwriting_fees"], "Underwriting fees",
         f"=B{P['total_gross']}*INPUTS!$B$8", None),
        (P["other_costs"], "Other offering costs", "=INPUTS!$B$9", None),
        (P["net_primary"], "Net primary proceeds to the company",
         f"=B{P['gross_primary']}*(1-INPUTS!$B$8)-B{P['other_costs']}", FILL_OUT),
        (P["net_secondary"], "Net secondary proceeds to selling holders",
         f"=B{P['gross_secondary']}*(1-INPUTS!$B$8)", None),
        (P["greenshoe_proceeds"], "Greenshoe proceeds (if exercised in full)",
         f"=OFFERING!B{O['greenshoe_shares']}*OFFERING!B{O['offer_price']}", None),
    ]:
        label(ws, r, lab)
        put(ws, f"B{r}", formula, fmt=NUM, fill=fill)

    ws.cell(row=P["uses_header"], column=1,
            value="Use of proceeds (company's net primary only)").font = F_TITLE
    ws.cell(row=P["uses_header"], column=3, value="Basis / source").font = F_SUB
    for k, u in enumerate(uses):
        r = P["uses_first"] + k
        label(ws, r, u["purpose"])
        put(ws, f"B{r}", u["amount"], font=F_INPUT, fmt=NUM)
        note(ws, r, 3, u.get("basis", ""))
    label(ws, P["uses_total"], "Total stated uses")
    put(ws, f"B{P['uses_total']}",
        f"=SUM(B{P['uses_first']}:B{P['uses_total'] - 1})", fmt=NUM)
    label(ws, P["uses_check"], "Unallocated (net primary − stated uses)")
    put(ws, f"B{P['uses_check']}",
        f"=B{P['net_primary']}-B{P['uses_total']}", fmt=NUM, fill=FILL_OUT)
    note(ws, P["uses_check"], 3,
         "A large unallocated balance is a finding, not an error — say so rather "
         "than inventing a purpose for it")

    widths(ws, {"A": 46, "B": 18, "C": 58})
    return ws


def build_sensitivity(wb, spec):
    """Offer price across peer multiple and IPO discount -- the two swing factors."""
    ws = wb.create_sheet("SENSITIVITY")
    V, S = IPOC["VALUATION"], IPOC["SENSITIVITY"]

    ws["A1"] = "SENSITIVITY — offer price: peer EV/EBITDA vs IPO discount"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("Only the EV/EBITDA leg of the blend moves with the x-axis; the "
                "other two methods hold, which is what a real re-mark looks like.")
    ws["A2"].font = F_NOTE
    ws.cell(row=S["x_row"] - 1, column=2,
            value="Peer EV/EBITDA ↓ / IPO discount →").font = F_SUB

    for k in range(GRID):
        c = col(S["grid_first_col"] + k)
        put(ws, f"{c}{S['x_row']}",
            f"=INPUTS!$B$4+(COLUMN({c}{S['x_row']})-"
            f"{S['grid_first_col'] + GRID // 2})*INPUTS!$B$17",
            font=F_SUB, fmt=PCT, fill=FILL_BAND)
    for j in range(GRID):
        r = S["y_start"] + j
        put(ws, f"B{r}",
            f"=VALUATION!$B${V['peer_ev_ebitda']}+(ROW(B{r})-"
            f"{S['y_start'] + GRID // 2})*INPUTS!$B$16",
            font=F_SUB, fmt=MULT, fill=FILL_BAND)

    for k in range(GRID):
        xc = col(S["grid_first_col"] + k)
        for j in range(GRID):
            r = S["y_start"] + j
            eq_a = f"($B{r}*VALUATION!$B${V['ntm_ebitda']}-INPUTS!$B$11)"
            blend = (f"(INPUTS!$B$13*{eq_a}"
                     f"+INPUTS!$B$14*VALUATION!$B${V['equity_ev_sales']}"
                     f"+INPUTS!$B$15*VALUATION!$B${V['equity_pe']})")
            put(ws, f"{xc}{r}",
                f"=IF({blend}<=0,NA(),{blend}*(1-{xc}${S['x_row']})/INPUTS!$B$7)",
                fmt=CUR,
                fill=FILL_OUT if (j == GRID // 2 and k == GRID // 2) else None)

    ws.cell(row=S["y_start"] + GRID + 1, column=2,
            value="Shaded centre cell = base case; it must equal the offer price "
                  "on OFFERING (CHECKS verifies this).").font = F_NOTE
    year_widths(ws, GRID + 1, label_w=28, year_w=13)
    return ws


def build_checks(wb, spec):
    nu = len(spec.get("use_of_proceeds", []))
    V, O, I = IPOC["VALUATION"], IPOC["OFFERING"], IPOC["INPUTS"]
    P, S = proceeds_rows(nu), IPOC["SENSITIVITY"]
    cc = col(S["grid_first_col"] + GRID // 2)
    cr = S["y_start"] + GRID // 2

    return checks_sheet(wb, [
        ("Valuation weights sum to 100%",
         '=IF(ABS(INPUTS!$B$13+INPUTS!$B$14+INPUTS!$B$15-1)<0.0001,"PASS","FAIL")',
         "The blend is a weighted average, not an accident"),
        ("Post-money value per share equals the offer price",
         f'=IF(ABS(OFFERING!B{O["post_money"]}/OFFERING!B{O["post_shares"]}'
         f'-OFFERING!B{O["offer_price"]})<0.0001,"PASS","FAIL")',
         "Primary shares were solved at the offer price, so the two must agree"),
        ("Primary shares raise exactly the proceeds target",
         f'=IF(ABS(OFFERING!B{O["primary_shares"]}*OFFERING!B{O["offer_price"]}'
         f'-INPUTS!$B$5)<0.01,"PASS","FAIL")',
         "Shares issued x price = gross primary proceeds"),
        ("Pre-money plus proceeds equals post-money",
         f'=IF(ABS(OFFERING!B{O["post_money"]}-(OFFERING!B{O["pre_money"]}'
         f'+INPUTS!$B$5))<0.01,"PASS","FAIL")',
         "No value appears or disappears at the moment of issue"),
        ("Offer price is positive",
         f'=IF(OFFERING!B{O["offer_price"]}>0,"PASS","FAIL")',
         "A non-positive price means the blend or the discount is wrong"),
        ("IPO discount between 0% and 100%",
         '=IF(AND(INPUTS!$B$4>=0,INPUTS!$B$4<1),"PASS","FAIL")',
         "A discount outside this range is a data error"),
        ("Free float does not exceed 100%",
         f'=IF(OFFERING!B{O["free_float_shoe"]}<=1,"PASS","FAIL")',
         "Shares offered cannot exceed shares outstanding"),
        ("Net primary proceeds below gross",
         f'=IF(PROCEEDS!B{P["net_primary"]}<PROCEEDS!B{P["gross_primary"]},'
         f'"PASS","FAIL")',
         "Fees and costs are actually deducted"),
        ("Sensitivity centre equals the offer price",
         f'=IF(ABS(SENSITIVITY!{cc}{cr}-OFFERING!B{O["offer_price"]})<0.0001,'
         f'"PASS","FAIL")',
         "The grid is wired to the same valuation"),
        ("Implied multiple at or below the peer median",
         f'=IF(OFFERING!B{O["implied_ev_ebitda"]}'
         f'<=VALUATION!B{V["peer_ev_ebitda"]},"PASS","REVIEW")',
         "An IPO pricing above its peer set is unusual enough to need saying"),
        ("Use of proceeds fully allocated",
         f'=IF(ABS(PROCEEDS!B{P["uses_check"]})<0.01,"PASS","REVIEW")',
         "REVIEW means a balance is unallocated — report it, do not invent a use"),
        ("Free float at or above 15%",
         f'=IF(OFFERING!B{O["free_float"]}>=0.15,"PASS","REVIEW")',
         "Most exchanges require a minimum float; below this, check the rule "
         "for the listing venue"),
    ])


def build(spec, out_path):
    wb = Workbook()
    wb.remove(wb.active)
    readme_sheet(wb, spec, "IPO pricing model", [
        ("History", f"{core.n_hist(spec)} reported years"),
        ("Pricing", "A weighted blend of three peer methods on NTM figures, "
                    "then an IPO discount"),
        ("Primary vs secondary", "Primary shares raise money for the company; "
                                 "secondary shares transfer ownership and raise "
                                 "nothing for it"),
        ("Greenshoe", "Shown at full exercise; it is an option, not a certainty"),
    ])
    build_inputs(wb, spec)
    build_historicals(wb, spec)
    build_valuation(wb, spec)
    build_offering(wb, spec)
    build_proceeds(wb, spec)
    build_sensitivity(wb, spec)
    build_checks(wb, spec)
    wb.save(out_path)
    return out_path
