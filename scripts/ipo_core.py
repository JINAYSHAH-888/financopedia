"""
Independent IPO engine.

Prices an offering from peer multiples, applies an IPO discount, splits the
offer into primary and secondary, and works out what the company actually
receives and who ends up owning what.

Conventions worth knowing when reading the workbook:

* Pre-money equity value is a weighted blend of three peer-based methods
  (EV/EBITDA, EV/Sales, P/E) on next-twelve-months figures. The weights are
  inputs, so the blend is visible rather than buried.
* The IPO discount is applied to that blend. It is the single most judgemental
  number in the model, which is why it is one axis of the sensitivity grid.
* Offer price = pre-money equity / pre-IPO shares. Primary shares are then
  solved from the proceeds target at that price, which keeps the post-money
  value per share identical to the offer price -- an identity the CHECKS tab
  tests.
* Secondary shares transfer ownership; they raise nothing for the company.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import dcf_core as core
from dcf_core import SpecError

REQUIRED_HIST = ["years", "revenue", "ebitda", "net_income"]

SCALARS = ["ipo_discount", "primary_proceeds_target", "secondary_shares",
           "pre_ipo_shares", "underwriting_fee_pct", "other_offering_costs",
           "greenshoe_pct", "net_debt", "price_range_pct",
           "weight_ev_ebitda", "weight_ev_sales", "weight_pe",
           "multiple_step", "discount_step"]

VECTORS = ["rev_growth", "ebitda_margin", "net_margin"]

PRESENTATION = {"multiple_step", "discount_step"}


def validate(spec: Dict[str, Any]) -> None:
    problems: List[str] = []
    core.validate_common(spec, problems)
    core.validate_hist_vectors(spec, REQUIRED_HIST, problems)
    core.validate_inputs(spec, SCALARS, VECTORS, problems, PRESENTATION)

    comps = spec.get("comps", [])
    if not comps:
        problems.append("comps is required -- an IPO is priced off peers")
    for k, c in enumerate(comps):
        for key in ("name", "ev_ebitda", "ev_sales", "pe"):
            if key not in c:
                problems.append(f"comps[{k}].{key} is required")
        if not c.get("source"):
            problems.append(f"comps[{k}].source is required")

    for k, u in enumerate(spec.get("use_of_proceeds", [])):
        for key in ("purpose", "amount"):
            if key not in u:
                problems.append(f"use_of_proceeds[{k}].{key} is required")
        if not u.get("basis"):
            problems.append(f"use_of_proceeds[{k}].basis is required")

    if problems:
        raise SpecError("spec validation failed:\n  - " + "\n  - ".join(problems))

    i = spec["inputs"]
    w = i["weight_ev_ebitda"] + i["weight_ev_sales"] + i["weight_pe"]
    if abs(w - 1.0) > 1e-6:
        raise SpecError(f"valuation weights sum to {w:.4f}, not 1.0 -- the blend "
                        "would be meaningless")
    if not (0.0 <= i["ipo_discount"] < 1.0):
        raise SpecError(f"ipo_discount of {i['ipo_discount']:.3f} is outside 0-1")


def median(xs: List[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


@dataclass
class Ipo:
    ntm_revenue: float = 0.0
    ntm_ebitda: float = 0.0
    ntm_net_income: float = 0.0
    peer_ev_ebitda: float = 0.0
    peer_ev_sales: float = 0.0
    peer_pe: float = 0.0
    equity_ev_ebitda: float = 0.0
    equity_ev_sales: float = 0.0
    equity_pe: float = 0.0
    blended_equity: float = 0.0
    pre_money: float = 0.0
    offer_price: float = 0.0
    primary_shares: float = 0.0
    post_shares: float = 0.0
    post_money: float = 0.0
    gross_primary: float = 0.0
    gross_secondary: float = 0.0
    total_gross: float = 0.0
    underwriting_fees: float = 0.0
    net_primary: float = 0.0
    net_secondary: float = 0.0
    greenshoe_shares: float = 0.0
    greenshoe_proceeds: float = 0.0
    base_shares_offered: float = 0.0
    free_float: float = 0.0
    free_float_with_shoe: float = 0.0
    dilution: float = 0.0
    post_net_debt: float = 0.0
    post_ev: float = 0.0
    implied_ev_ebitda: float = 0.0
    implied_pe: float = 0.0
    discount_to_peers_ebitda: float = 0.0
    price_low: float = 0.0
    price_high: float = 0.0
    use_of_proceeds_total: float = 0.0
    use_of_proceeds_gap: float = 0.0


def run(spec: Dict[str, Any]) -> Ipo:
    i, h, comps = spec["inputs"], spec["historicals"], spec["comps"]
    r = Ipo()

    r.ntm_revenue = h["revenue"][-1] * (1 + i["rev_growth"][0])
    r.ntm_ebitda = r.ntm_revenue * i["ebitda_margin"][0]
    r.ntm_net_income = r.ntm_revenue * i["net_margin"][0]

    r.peer_ev_ebitda = median([c["ev_ebitda"] for c in comps])
    r.peer_ev_sales = median([c["ev_sales"] for c in comps])
    r.peer_pe = median([c["pe"] for c in comps])

    r.equity_ev_ebitda = r.peer_ev_ebitda * r.ntm_ebitda - i["net_debt"]
    r.equity_ev_sales = r.peer_ev_sales * r.ntm_revenue - i["net_debt"]
    r.equity_pe = r.peer_pe * r.ntm_net_income

    r.blended_equity = (i["weight_ev_ebitda"] * r.equity_ev_ebitda
                        + i["weight_ev_sales"] * r.equity_ev_sales
                        + i["weight_pe"] * r.equity_pe)
    r.pre_money = r.blended_equity * (1 - i["ipo_discount"])
    r.offer_price = r.pre_money / i["pre_ipo_shares"]

    r.primary_shares = i["primary_proceeds_target"] / r.offer_price
    r.post_shares = i["pre_ipo_shares"] + r.primary_shares
    r.post_money = r.pre_money + i["primary_proceeds_target"]

    r.gross_primary = i["primary_proceeds_target"]
    r.gross_secondary = i["secondary_shares"] * r.offer_price
    r.total_gross = r.gross_primary + r.gross_secondary
    r.underwriting_fees = r.total_gross * i["underwriting_fee_pct"]
    r.net_primary = (r.gross_primary * (1 - i["underwriting_fee_pct"])
                     - i["other_offering_costs"])
    r.net_secondary = r.gross_secondary * (1 - i["underwriting_fee_pct"])

    r.base_shares_offered = r.primary_shares + i["secondary_shares"]
    r.greenshoe_shares = r.base_shares_offered * i["greenshoe_pct"]
    r.greenshoe_proceeds = r.greenshoe_shares * r.offer_price

    r.free_float = r.base_shares_offered / r.post_shares
    r.free_float_with_shoe = ((r.base_shares_offered + r.greenshoe_shares)
                              / r.post_shares)
    r.dilution = r.primary_shares / r.post_shares

    r.post_net_debt = i["net_debt"] - r.net_primary
    r.post_ev = r.post_money + r.post_net_debt
    r.implied_ev_ebitda = r.post_ev / r.ntm_ebitda if r.ntm_ebitda else float("nan")
    r.implied_pe = (r.post_money / r.ntm_net_income
                    if r.ntm_net_income else float("nan"))
    r.discount_to_peers_ebitda = (r.implied_ev_ebitda / r.peer_ev_ebitda - 1
                                  if r.peer_ev_ebitda else float("nan"))

    r.price_low = r.offer_price * (1 - i["price_range_pct"])
    r.price_high = r.offer_price * (1 + i["price_range_pct"])

    uses = spec.get("use_of_proceeds", [])
    r.use_of_proceeds_total = sum(u["amount"] for u in uses)
    r.use_of_proceeds_gap = r.use_of_proceeds_total - r.net_primary
    return r


def offer_price_at(spec: Dict[str, Any], peer_multiple: float,
                   discount: float, r: Ipo) -> float:
    """Offer price for a grid cell: vary the EBITDA multiple and the discount."""
    i = spec["inputs"]
    eq_a = peer_multiple * r.ntm_ebitda - i["net_debt"]
    blended = (i["weight_ev_ebitda"] * eq_a
               + i["weight_ev_sales"] * r.equity_ev_sales
               + i["weight_pe"] * r.equity_pe)
    return blended * (1 - discount) / i["pre_ipo_shares"]
