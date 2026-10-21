#!/usr/bin/env python3
"""
Charts for the research report.

Built to the dataviz method: the form follows the data's job, categorical hues
are assigned in fixed order and never cycled, one y-axis only, and the palette
is the validated default instance (six slots, all checks pass light-mode).

Three of those slots sit below 3:1 contrast on a light surface, which triggers
the relief rule — so every chart here ships **direct labels** and the report
renders a data table beneath each figure. That satisfies the relief obligation
and the accessibility pass, and it suits print: a PDF has no hover layer, so
anything a tooltip would have carried has to be on the page.

    python3 research_charts.py bundle.json --outdir charts/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# Validated default categorical palette, light mode, in fixed order.
# Never cycled: a seventh series folds into "Other" or the chart is faceted.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
MAX_SERIES = len(SERIES)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#8a8982"
GRID = "#e4e3de"

# status palette, reserved — never reused as a series colour
STATUS = {"good": "#1a7f4b", "warning": "#b26a00", "critical": "#b3261e"}

FORMS = ["timeseries", "estimate_range", "composition", "bars", "waterfall"]


def _style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "legend.frameon": False,
        "legend.fontsize": 8.5,
    })


def _recessive_axes(ax, y_grid=True):
    """Grid and axes stay in the background; the data is the figure."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    if y_grid:
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, color=GRID, linewidth=0.7)
        ax.xaxis.grid(False)


def _fmt(unit: str):
    """Axis formatter that keeps large money readable without a dual axis."""
    def f(v, _pos):
        a = abs(v)
        if a >= 1_000_000:
            s = f"{v / 1_000_000:,.1f}M"
        elif a >= 1_000:
            s = f"{v / 1_000:,.1f}k"
        elif a < 1 and a > 0:
            return f"{v:.0%}" if unit == "%" else f"{v:,.2f}"
        else:
            s = f"{v:,.0f}"
        return s
    return FuncFormatter(f)


def _label_point(ax, x, y, text, color, dy=8):
    ax.annotate(text, (x, y), textcoords="offset points", xytext=(0, dy),
                ha="center", fontsize=8, color=INK, fontweight="bold")


# --------------------------------------------------------------------------
# forms
# --------------------------------------------------------------------------


def chart_timeseries(spec, ax):
    """Change over time. Lines at 2px, >=8px markers, first and last labelled."""
    unit = spec.get("unit", "")
    series = spec["series"]
    if len(series) > MAX_SERIES:
        raise ValueError(f"{spec['id']}: {len(series)} series exceeds the "
                         f"{MAX_SERIES}-slot palette — fold the tail into "
                         "'Other' or facet the chart")
    for k, s in enumerate(series):
        c = SERIES[k]
        ax.plot(spec["x"], s["values"], color=c, linewidth=2.0,
                marker="o", markersize=4.5, markerfacecolor=c,
                markeredgecolor=SURFACE, markeredgewidth=1.2,
                label=s["name"], zorder=3 + k)
        # selective direct labels: endpoints only, never every point
        _label_point(ax, spec["x"][-1], s["values"][-1],
                     f"{s['values'][-1]:,.0f}", c)
    ax.yaxis.set_major_formatter(_fmt(unit))
    # a year axis is categorical, not continuous: without this matplotlib
    # happily labels 2022.5, which is not a year
    ax.set_xticks(list(spec["x"]))
    ax.set_xticklabels([str(v) for v in spec["x"]])
    _recessive_axes(ax)
    if len(series) > 1:
        ax.legend(loc="upper left", ncol=min(len(series), 3),
                  bbox_to_anchor=(0, 1.0))
    if unit:
        ax.set_ylabel(unit)


def chart_estimate_range(spec, ax):
    """The signature chart of this module: who forecasts what, and the spread.

    A dot plot rather than bars, because these are point estimates from
    different authors, not parts of a whole — and a bar chart would imply a
    magnitude comparison that starts at zero and invites averaging.
    """
    rows = sorted(spec["estimates"], key=lambda r: r["value"])
    ypos = list(range(len(rows)))
    lo = min(r["value"] for r in rows)
    hi = max(r["value"] for r in rows)

    # the range itself, drawn once behind the points
    ax.plot([lo, hi], [-0.8, -0.8], color=INK_MUTED, linewidth=2.0,
            solid_capstyle="round", zorder=2)
    ax.annotate(f"spread {hi / lo:.2f}x", ((lo + hi) / 2, -0.8),
                textcoords="offset points", xytext=(0, -14), ha="center",
                fontsize=8, color=INK_2, style="italic")

    for k, r in enumerate(rows):
        # restatements are not independent, and the chart says so rather than
        # letting them read as corroboration
        restated = bool(r.get("upstream"))
        c = SERIES[2] if not restated else INK_MUTED
        ax.plot([r["value"]], [ypos[k]], marker="o", markersize=9,
                color=c, markeredgecolor=SURFACE, markeredgewidth=1.5,
                zorder=4, linestyle="none")
        ax.annotate(f"{r['value']:,.0f}", (r["value"], ypos[k]),
                    textcoords="offset points", xytext=(12, 0), va="center",
                    fontsize=8.5, color=INK, fontweight="bold")
        if restated:
            ax.annotate(f"restates {r['upstream']}", (r["value"], ypos[k]),
                        textcoords="offset points", xytext=(12, -11),
                        va="center", fontsize=7, color=INK_MUTED,
                        style="italic")

    ax.set_yticks(ypos)
    ax.set_yticklabels([f"{r['author']}  ({r['published']})" for r in rows])
    ax.set_ylim(-1.6, len(rows) - 0.4)
    ax.set_xlim(lo * 0.82, hi * 1.22)
    ax.xaxis.set_major_formatter(_fmt(spec.get("unit", "")))
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=GRID, linewidth=0.7)
    ax.yaxis.grid(False)
    ax.tick_params(axis="y", length=0)
    if spec.get("unit"):
        ax.set_xlabel(spec["unit"])


def chart_composition(spec, ax):
    """Shares of a whole over time: stacked bars with a 2px surface gap."""
    series = spec["series"]
    if len(series) > MAX_SERIES:
        raise ValueError(f"{spec['id']}: {len(series)} series exceeds the "
                         f"{MAX_SERIES}-slot palette — fold the tail into 'Other'")
    x = list(range(len(spec["x"])))
    bottom = [0.0] * len(x)
    for k, s in enumerate(series):
        ax.bar(x, s["values"], bottom=bottom, color=SERIES[k], width=0.62,
               label=s["name"], edgecolor=SURFACE, linewidth=2.0, zorder=3)
        for i, v in enumerate(s["values"]):
            if v / max(sum(col) for col in zip(*[q["values"] for q in series])) > 0.07:
                ax.annotate(f"{v:,.0f}", (x[i], bottom[i] + v / 2),
                            ha="center", va="center", fontsize=7.5,
                            color="#ffffff", fontweight="bold")
        bottom = [b + v for b, v in zip(bottom, s["values"])]
    ax.set_xticks(x)
    ax.set_xticklabels(spec["x"])
    ax.yaxis.set_major_formatter(_fmt(spec.get("unit", "")))
    _recessive_axes(ax)
    ax.legend(loc="upper left", ncol=min(len(series), 3))
    if spec.get("unit"):
        ax.set_ylabel(spec["unit"])


def chart_bars(spec, ax):
    """Magnitude across categories. One series, sorted, directly labelled."""
    rows = list(zip(spec["x"], spec["series"][0]["values"]))
    if spec.get("sort", True):
        rows.sort(key=lambda r: r[1], reverse=True)
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    y = list(range(len(vals)))
    ax.barh(y, vals, color=SERIES[0], height=0.62, zorder=3,
            edgecolor=SURFACE, linewidth=2.0)
    for k, v in enumerate(vals):
        ax.annotate(f"{v:,.1f}", (v, y[k]), textcoords="offset points",
                    xytext=(6, 0), va="center", fontsize=8.5, color=INK,
                    fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.18)
    ax.xaxis.set_major_formatter(_fmt(spec.get("unit", "")))
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=GRID, linewidth=0.7)
    ax.tick_params(axis="y", length=0)
    if spec.get("unit"):
        ax.set_xlabel(spec["unit"])


def chart_waterfall(spec, ax):
    """What builds to a total. Status colours here carry polarity, not identity."""
    labels = spec["x"]
    vals = spec["series"][0]["values"]
    running = 0.0
    for k, v in enumerate(vals):
        is_total = bool(spec.get("totals", [False] * len(vals))[k])
        if is_total:
            ax.bar(k, v, bottom=0, color=INK_2, width=0.6, zorder=3,
                   edgecolor=SURFACE, linewidth=2.0)
            top = v
        else:
            c = STATUS["good"] if v >= 0 else STATUS["critical"]
            ax.bar(k, v, bottom=running, color=c, width=0.6, zorder=3,
                   edgecolor=SURFACE, linewidth=2.0)
            running += v
            top = running
        ax.annotate(f"{v:+,.1f}" if not is_total else f"{v:,.1f}",
                    (k, top), textcoords="offset points",
                    xytext=(0, 5 if v >= 0 or is_total else -13),
                    ha="center", fontsize=8, color=INK, fontweight="bold")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.axhline(0, color=GRID, linewidth=1.0)
    ax.yaxis.set_major_formatter(_fmt(spec.get("unit", "")))
    _recessive_axes(ax)
    if spec.get("unit"):
        ax.set_ylabel(spec["unit"])


BUILDERS = {
    "timeseries": chart_timeseries,
    "estimate_range": chart_estimate_range,
    "composition": chart_composition,
    "bars": chart_bars,
    "waterfall": chart_waterfall,
}


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def validate_charts(bundle: Dict[str, Any], problems: List[str]) -> None:
    for k, c in enumerate(bundle.get("charts", [])):
        tag = c.get("id", f"charts[{k}]")
        if c.get("form") not in BUILDERS:
            problems.append(f"{tag}.form must be one of {sorted(BUILDERS)}")
            continue
        if not c.get("title"):
            problems.append(f"{tag}.title is required")
        if not c.get("cites"):
            problems.append(f"{tag}.cites is required — a chart carries the "
                            "source markers for the data it draws")
        if c["form"] == "estimate_range":
            if not c.get("estimates"):
                problems.append(f"{tag}.estimates is required for an "
                                "estimate_range chart")
            continue
        if not c.get("x"):
            problems.append(f"{tag}.x is required")
        if not c.get("series"):
            problems.append(f"{tag}.series is required")
            continue
        for s in c["series"]:
            if len(s.get("values", [])) != len(c.get("x", [])):
                problems.append(f"{tag}: series '{s.get('name')}' has "
                                f"{len(s.get('values', []))} values but "
                                f"{len(c.get('x', []))} x positions")
        if len(c["series"]) > MAX_SERIES:
            problems.append(f"{tag}: {len(c['series'])} series exceeds the "
                            f"{MAX_SERIES}-slot palette — hues are never "
                            "cycled, so fold the tail into 'Other' or facet")


def render(bundle: Dict[str, Any], outdir: str) -> List[Dict[str, Any]]:
    _style()
    os.makedirs(outdir, exist_ok=True)
    out = []
    for c in bundle.get("charts", []):
        h = c.get("height", 3.3)
        fig, ax = plt.subplots(figsize=(7.1, h), dpi=200)
        BUILDERS[c["form"]](c, ax)
        # the subtitle sits between the title and the plot, so the title's
        # pad has to clear it or the two overprint
        has_sub = bool(c.get("subtitle"))
        ax.set_title(c["title"], loc="left", pad=26 if has_sub else 12)
        if has_sub:
            ax.annotate(c["subtitle"], xy=(0, 1.0), xycoords="axes fraction",
                        xytext=(0, 9), textcoords="offset points",
                        fontsize=8.5, color=INK_2)
        fig.tight_layout()
        path = os.path.join(outdir, f"{c['id']}.png")
        fig.savefig(path, bbox_inches="tight", pad_inches=0.18)
        plt.close(fig)
        out.append({"id": c["id"], "path": path, "title": c["title"],
                    "cites": c.get("cites", [])})
    return out


def table_for(c: Dict[str, Any]) -> List[List[str]]:
    """The data table that ships beneath each chart.

    Required, not optional: it discharges the relief rule for the three
    low-contrast palette slots, and a PDF has no hover layer, so the numbers
    have to be on the page.
    """
    if c["form"] == "estimate_range":
        head = ["Author", "Published", "Value", "Basis"]
        rows = [[r["author"], str(r["published"]), f"{r['value']:,.0f}",
                 ("restates " + r["upstream"]) if r.get("upstream") else "original"]
                for r in sorted(c["estimates"], key=lambda r: r["value"])]
        return [head] + rows
    head = [c.get("x_label", "")] + [s["name"] for s in c["series"]]
    rows = []
    for i, xv in enumerate(c["x"]):
        rows.append([str(xv)] + [f"{s['values'][i]:,.1f}" for s in c["series"]])
    return [head] + rows


def main():
    ap = argparse.ArgumentParser(description="Render research charts")
    ap.add_argument("bundle")
    ap.add_argument("--outdir", default="charts")
    args = ap.parse_args()

    with open(args.bundle, "r", encoding="utf-8") as fh:
        bundle = json.load(fh)
    problems: List[str] = []
    validate_charts(bundle, problems)
    if problems:
        print("chart validation failed:")
        for p in problems:
            print(f"  - {p}")
        return 1
    made = render(bundle, args.outdir)
    for m in made:
        print(f"  {m['id']:<28} {m['path']}")
    print(f"{len(made)} charts written to {args.outdir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
