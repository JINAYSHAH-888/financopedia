#!/usr/bin/env python3
"""
The estimate layer: published forecasts, handled as forecasts.

"The market will reach $47bn by 2030" is not a fact. It is someone's model,
run at some date, from some base, on some definition, possibly restating
someone else's work. This module keeps all of that attached to the number and
computes the things that make a set of forecasts interpretable:

* the implied CAGR, recomputed from base and target -- which disagrees with
  the stated growth rate more often than you would expect, and when it does,
  one of the published figures is wrong;
* the spread, because a market whose forecasts span 2.5x is a market nobody
  can size, and that is the finding rather than a nuisance to be averaged away;
* the independence count, because five outlets citing one consultancy is one
  estimate, not five;
* stale vintages, because a forecast whose horizon has partly elapsed can be
  scored against what actually happened.

Deliberately absent: any function that averages published forecasts into a
single number. That operation destroys exactly the information this module
exists to preserve.

    python3 estimate_core.py bundle.json --report
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

REQUIRED = ["id", "subject", "author", "published", "base_year", "base_value",
            "target_year", "target_value", "unit", "source"]

OPTIONAL = ["method", "upstream", "scope", "geography", "stated_cagr", "notes"]


class EstimateError(ValueError):
    pass


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def validate(estimates: List[Dict[str, Any]], problems: List[str]) -> None:
    seen = set()
    for k, e in enumerate(estimates):
        tag = e.get("id", f"estimates[{k}]")
        for key in REQUIRED:
            if e.get(key) in (None, ""):
                problems.append(f"{tag}.{key} is required — an estimate without "
                                "it cannot be attributed or checked")
        if e.get("id") in seen:
            problems.append(f"duplicate estimate id: {e['id']}")
        seen.add(e.get("id"))

        ty, by = e.get("target_year"), e.get("base_year")
        if isinstance(ty, int) and isinstance(by, int) and ty <= by:
            problems.append(f"{tag}: target_year {ty} is not after base_year {by}")
        for key in ("base_value", "target_value"):
            v = e.get(key)
            if isinstance(v, (int, float)) and v <= 0:
                problems.append(f"{tag}.{key} must be positive to imply a growth rate")
        if e.get("upstream") and e.get("upstream") == e.get("author"):
            problems.append(f"{tag}: upstream equals author — leave upstream out "
                            "if this is original work")


# --------------------------------------------------------------------------
# the maths
# --------------------------------------------------------------------------


def implied_cagr(e: Dict[str, Any]) -> float:
    years = e["target_year"] - e["base_year"]
    if years <= 0 or e["base_value"] <= 0:
        return float("nan")
    return (e["target_value"] / e["base_value"]) ** (1.0 / years) - 1.0


def median(xs: List[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if not n:
        return float("nan")
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def analyse(estimates: List[Dict[str, Any]], as_of_year: int) -> Dict[str, Any]:
    """Everything the report needs about a set of estimates for one subject."""
    rows = []
    for e in estimates:
        cagr = implied_cagr(e)
        stated = e.get("stated_cagr")
        row = {
            **{k: e.get(k) for k in REQUIRED + OPTIONAL},
            "implied_cagr": cagr,
            "cagr_mismatch": (abs(cagr - stated) > 0.005
                              if isinstance(stated, (int, float)) else None),
            "horizon_years": e["target_year"] - e["base_year"],
            "scoreable": e["target_year"] <= as_of_year,
            "is_restatement": bool(e.get("upstream")),
        }
        rows.append(row)

    targets = [r["target_value"] for r in rows]
    cagrs = [r["implied_cagr"] for r in rows if r["implied_cagr"] == r["implied_cagr"]]

    # independence: an estimate restating someone else's work is not its own
    # data point. Group by upstream where present, by author where not.
    lineages: Dict[str, List[str]] = {}
    for r in rows:
        key = r["upstream"] or r["author"]
        lineages.setdefault(key, []).append(r["id"])

    scopes = {(r.get("scope"), r.get("geography")) for r in rows}
    target_years = {r["target_year"] for r in rows}

    flags = []
    for r in rows:
        if r["cagr_mismatch"]:
            flags.append(f"{r['id']}: stated CAGR {r['stated_cagr']:.1%} does not "
                         f"match the {r['implied_cagr']:.1%} implied by its own "
                         "base and target — one of the published figures is wrong")
        if r["scoreable"]:
            flags.append(f"{r['id']}: target year {r['target_year']} has elapsed "
                         "— score this forecast against outturn rather than "
                         "repeating it as a forecast")
        if r["is_restatement"]:
            flags.append(f"{r['id']}: restates {r['upstream']} — not independent "
                         "corroboration")
    if len(scopes) > 1:
        flags.append(f"{len(scopes)} different scope/geography combinations — "
                     "these are not measuring the same thing and must not be "
                     "compared as if they were")
    if len(target_years) > 1:
        flags.append(f"target years differ ({sorted(target_years)}) — compare the "
                     "implied CAGRs, not the headline values")

    return {
        "rows": rows,
        "count": len(rows),
        "independent_count": len(lineages),
        "lineages": lineages,
        "target_low": min(targets) if targets else float("nan"),
        "target_high": max(targets) if targets else float("nan"),
        "target_median": median(targets),
        "spread_ratio": (max(targets) / min(targets)
                         if targets and min(targets) > 0 else float("nan")),
        "cagr_low": min(cagrs) if cagrs else float("nan"),
        "cagr_high": max(cagrs) if cagrs else float("nan"),
        "cagr_median": median(cagrs),
        "scopes": sorted(str(s) for s in scopes),
        "target_years": sorted(target_years),
        "flags": flags,
        "unit": rows[0]["unit"] if rows else "",
        "subject": rows[0]["subject"] if rows else "",
    }


def score_forecasts(estimates: List[Dict[str, Any]],
                    outturns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Score past forecasts against what actually happened.

    The most informative thing a research report can contain, and the most
    commonly omitted: a forecaster who was 40% high last cycle deserves less
    weight this cycle, and that is knowable.
    """
    index = {(o["subject"], o["year"]): o for o in outturns
             if isinstance(o.get("value"), (int, float)) and o["value"] > 0}
    scored = []
    for e in estimates:
        key = (e["subject"], e["target_year"])
        if key not in index:
            continue
        actual = index[key]
        err = e["target_value"] / actual["value"] - 1.0
        scored.append({
            "id": e["id"], "author": e["author"], "published": e["published"],
            "subject": e["subject"], "year": e["target_year"],
            "forecast": e["target_value"], "actual": actual["value"],
            "error": err, "actual_source": actual.get("source", ""),
            "verdict": ("over-forecast" if err > 0.05 else
                        "under-forecast" if err < -0.05 else "close"),
        })
    return scored


# --------------------------------------------------------------------------
# bundle-level entry point
# --------------------------------------------------------------------------


def load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def analyse_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    ests = bundle.get("estimates", [])
    as_of_year = int(str(bundle["meta"]["as_of"])[:4])
    by_subject: Dict[str, List[Dict[str, Any]]] = {}
    for e in ests:
        by_subject.setdefault(e["subject"], []).append(e)
    return {subj: analyse(rows, as_of_year) for subj, rows in by_subject.items()}


def main():
    ap = argparse.ArgumentParser(description="Analyse published estimates")
    ap.add_argument("bundle")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    bundle = load(args.bundle)
    problems: List[str] = []
    validate(bundle.get("estimates", []), problems)
    if problems:
        print("estimate validation failed:")
        for p in problems:
            print(f"  - {p}")
        return 1

    groups = analyse_bundle(bundle)
    if not groups:
        print("no estimates in the bundle")
        return 0

    for subj, g in groups.items():
        print(f"\n{subj} ({g['unit']})")
        print("=" * 78)
        print(f"{'id':<16}{'author':<24}{'published':<12}{'target':>10}{'CAGR':>9}")
        print("-" * 78)
        for r in sorted(g["rows"], key=lambda x: x["target_value"]):
            print(f"{r['id']:<16}{r['author'][:23]:<24}{str(r['published']):<12}"
                  f"{r['target_value']:>10,.0f}{r['implied_cagr']:>9.1%}")
        print("-" * 78)
        print(f"  range {g['target_low']:,.0f} – {g['target_high']:,.0f} "
              f"(median {g['target_median']:,.0f}, high/low {g['spread_ratio']:.2f}x)")
        print(f"  implied CAGR {g['cagr_low']:.1%} – {g['cagr_high']:.1%} "
              f"(median {g['cagr_median']:.1%})")
        print(f"  {g['count']} estimates, {g['independent_count']} independent "
              "lineage(s)")
        if g["independent_count"] < g["count"]:
            for parent, kids in g["lineages"].items():
                if len(kids) > 1:
                    print(f"    {parent}: {', '.join(kids)}")
        if g["flags"]:
            print("  flags:")
            for f in g["flags"]:
                print(f"    - {f}")

    outturns = bundle.get("outturns", [])
    if outturns:
        scored = score_forecasts(bundle["estimates"], outturns)
        if scored:
            print("\nPast forecasts scored against outturn")
            print("=" * 78)
            for s in scored:
                print(f"  {s['author'][:28]:<30}{s['year']}  forecast "
                      f"{s['forecast']:,.0f} vs actual {s['actual']:,.0f}  "
                      f"{s['error']:+.1%} ({s['verdict']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
