#!/usr/bin/env python3
"""
Assemble the research report as a PDF.

The citation resolver is the heart of this file. You write `[S:imf-weo-2026]`
in the bundle's prose; the builder assigns reference numbers in order of first
appearance and renders `[4]`, then emits the numbered reference list to match.
Numbers are never written by hand, because hand-written numbers drift the
moment a section moves.

    python3 build_report.py bundle.json -o research-topic.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from typing import Any, Dict, List, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import research_charts as rc  # noqa: E402

INK = colors.HexColor("#0b0b0b")
INK_2 = colors.HexColor("#52514e")
INK_MUTED = colors.HexColor("#8a8982")
RULE = colors.HexColor("#d8d7d1")
BAND = colors.HexColor("#f4f3ef")
ACCENT = colors.HexColor("#2a78d6")
SURFACE = colors.HexColor("#fcfcfb")

CONFIDENCE = {
    "well-evidenced": colors.HexColor("#1a7f4b"),
    "contested": colors.HexColor("#b26a00"),
    "thin": colors.HexColor("#b3261e"),
}

# Accepts both [S:key] and multi-key [S:a, b] or [S:a, S:b] — people write the
# prefix on every key as often as not, and a citation parser that silently
# fails to match is worse than no parser at all.
CITE = re.compile(r"\[S:\s*([^\]]+?)\s*\]")


def cite_keys(raw: str) -> List[str]:
    """Split a marker's payload into source keys, tolerating repeated 'S:'."""
    out = []
    for part in raw.split(","):
        k = part.strip()
        if k.upper().startswith("S:"):
            k = k[2:].strip()
        if k:
            out.append(k)
    return out


# --------------------------------------------------------------------------
# citation resolution
# --------------------------------------------------------------------------


class Citations:
    """Assigns reference numbers in order of first appearance.

    Keeping this in one object is what makes the numbering trustworthy: there
    is exactly one counter, it only ever increments, and `unused()` can prove
    afterwards that nothing in the reference list went uncited.
    """

    def __init__(self, sources: List[Dict[str, Any]]):
        self.sources = {s["key"]: s for s in sources}
        self.order: List[str] = []
        self.missing: List[str] = []

    def number(self, key: str) -> int:
        if key not in self.sources:
            if key not in self.missing:
                self.missing.append(key)
            return 0
        if key not in self.order:
            self.order.append(key)
        return self.order.index(key) + 1

    def render(self, text: str) -> str:
        """Replace every [S:key] marker with its resolved number."""
        def sub(m):
            resolved = []
            for k in cite_keys(m.group(1)):
                resolved.append(self.number(k))
            known = sorted(n for n in resolved if n)
            nums = [str(n) for n in known] + ["?"] * resolved.count(0)
            return "<super>[" + ", ".join(nums) + "]</super>"
        return CITE.sub(sub, text)

    def marker(self, keys: List[str]) -> str:
        resolved = [self.number(k) for k in keys]
        nums = [str(n) for n in sorted(n for n in resolved if n)]
        nums += ["?"] * resolved.count(0)
        return "[" + ", ".join(nums) + "]"

    def unused(self) -> List[str]:
        return [k for k in self.sources if k not in self.order]

    def reference_list(self) -> List[Tuple[int, Dict[str, Any]]]:
        return [(i + 1, self.sources[k]) for i, k in enumerate(self.order)]


# --------------------------------------------------------------------------
# styles
# --------------------------------------------------------------------------


def styles():
    ss = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold",
                                fontSize=21, leading=25, textColor=INK,
                                alignment=TA_LEFT, spaceAfter=2)
    s["subtitle"] = ParagraphStyle("st", fontName="Helvetica", fontSize=11,
                                   leading=15, textColor=INK_2, spaceAfter=10)
    s["meta"] = ParagraphStyle("m", fontName="Helvetica", fontSize=8,
                               leading=11, textColor=INK_MUTED)
    s["h1"] = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=13,
                             leading=16, textColor=INK, spaceBefore=14,
                             spaceAfter=5)
    s["h2"] = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5,
                             leading=13, textColor=INK, spaceBefore=9,
                             spaceAfter=3)
    s["body"] = ParagraphStyle("b", fontName="Helvetica", fontSize=9.6,
                               leading=14.2, textColor=INK,
                               alignment=TA_JUSTIFY, spaceAfter=7)
    s["lead"] = ParagraphStyle("l", fontName="Helvetica", fontSize=10.6,
                               leading=15.4, textColor=INK,
                               alignment=TA_JUSTIFY, spaceAfter=8)
    s["caption"] = ParagraphStyle("c", fontName="Helvetica-Oblique", fontSize=7.8,
                                  leading=10.5, textColor=INK_MUTED,
                                  spaceBefore=3, spaceAfter=2)
    s["finding"] = ParagraphStyle("f", fontName="Helvetica", fontSize=9.2,
                                  leading=12.6, textColor=INK)
    s["findlabel"] = ParagraphStyle("fl", fontName="Helvetica-Bold", fontSize=7.2,
                                    leading=9, textColor=colors.white)
    s["ref"] = ParagraphStyle("r", fontName="Helvetica", fontSize=8.1,
                              leading=11.4, textColor=INK_2, spaceAfter=3)
    s["cell"] = ParagraphStyle("cl", fontName="Helvetica", fontSize=7.6,
                               leading=10, textColor=INK)
    s["cellh"] = ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=7.6,
                                leading=10, textColor=colors.white)
    s["note"] = ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=8.4,
                               leading=11.6, textColor=INK_2, spaceAfter=6)
    return s


def data_table(rows: List[List[str]], widths=None) -> Table:
    st = styles()
    body = [[Paragraph(str(c), st["cellh"] if i == 0 else st["cell"])
             for c in row] for i, row in enumerate(rows)]
    t = Table(body, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK_2),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE, BAND]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# --------------------------------------------------------------------------
# page furniture
# --------------------------------------------------------------------------


def make_doc(path, meta):
    doc = BaseDocTemplate(path, pagesize=A4,
                          leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=18 * mm, bottomMargin=17 * mm,
                          title=meta.get("title", "Research report"),
                          author=meta.get("author", "Financopedia"))
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="body")

    def decorate(canvas, d):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        y = A4[1] - 13 * mm
        canvas.line(d.leftMargin, y, A4[0] - d.rightMargin, y)
        canvas.setFont("Helvetica", 7.2)
        canvas.setFillColor(INK_MUTED)
        canvas.drawString(d.leftMargin, y + 2.5 * mm,
                          meta.get("title", "")[:95])
        canvas.drawRightString(A4[0] - d.rightMargin, y + 2.5 * mm,
                               f"as of {meta.get('as_of', '')}")
        canvas.line(d.leftMargin, 13 * mm, A4[0] - d.rightMargin, 13 * mm)
        canvas.drawString(d.leftMargin, 9 * mm,
                          "Research and analysis only — not investment advice.")
        canvas.drawRightString(A4[0] - d.rightMargin, 9 * mm,
                               f"{canvas.getPageNumber()}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=decorate)])
    return doc


# --------------------------------------------------------------------------
# blocks
# --------------------------------------------------------------------------


def key_findings(bundle, cites, st) -> List[Any]:
    """The infographic strip: what gets read when nothing else does."""
    out = [Paragraph("Key findings", st["h1"])]
    rows = []
    for k, f in enumerate(bundle.get("key_findings", []), start=1):
        conf = f.get("confidence", "thin")
        chip = Table([[Paragraph(conf.upper(), st["findlabel"])]],
                     colWidths=[26 * mm], rowHeights=[6.4 * mm])
        chip.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), CONFIDENCE.get(conf, INK_MUTED)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))
        num = Paragraph(f"<font color='#2a78d6'><b>{k}</b></font>", st["finding"])
        txt = Paragraph(cites.render(f["text"]), st["finding"])
        rows.append([num, txt, chip])
    if not rows:
        return []
    t = Table(rows, colWidths=[7 * mm, 115 * mm, 28 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 7),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 7),
    ]))
    out.append(t)
    out.append(Spacer(1, 4))
    return out


def chart_block(chart, rendered, cites, st) -> List[Any]:
    """A figure: image, caption with its citations, and the data table.

    The table is not optional — three slots of the palette sit below 3:1
    contrast on a light surface, which obliges visible relief, and a PDF has
    no hover layer to carry the numbers.
    """
    path = rendered[chart["id"]]
    img = Image(path)
    avail = 170 * mm
    iw, ih = img.imageWidth, img.imageHeight
    img.drawWidth = avail
    img.drawHeight = ih * (avail / iw)

    title = chart["title"].rstrip()
    if not title.endswith((".", "!", "?")):
        title += "."
    cap = f"<b>Figure {chart['_fignum']}.</b> {title}"
    if chart.get("note"):
        note_txt = chart["note"].rstrip()
        if not note_txt.endswith((".", "!", "?")):
            note_txt += "."
        cap += f" {note_txt}"
    cap += f" Source: {cites.marker(chart.get('cites', []))}"

    parts = [img, Paragraph(cap, st["caption"])]
    rows = rc.table_for(chart)
    ncol = len(rows[0])
    widths = [max(26 * mm, (170 * mm) / ncol)] * ncol
    if sum(widths) > 170 * mm:
        widths = [170 * mm / ncol] * ncol
    parts.append(data_table(rows, widths))
    parts.append(Spacer(1, 9))
    return [KeepTogether(parts[:2]), parts[2], parts[3]]


def estimate_table(bundle, cites, st) -> List[Any]:
    """The comparison table: every forecast with its provenance and its spread."""
    import estimate_core as ec
    groups = ec.analyse_bundle(bundle)
    if not groups:
        return []
    out = [Paragraph("Published estimates, compared", st["h1"])]
    out.append(Paragraph(
        "Published forecasts are models, not measurements. Each is shown with "
        "its author, vintage, base year and implied compound growth rate, so "
        "the spread and its causes are visible. They are deliberately not "
        "averaged: a single blended figure would conceal exactly the "
        "disagreement that matters.", st["note"]))
    for subj, g in groups.items():
        out.append(Paragraph(f"{subj} ({g['unit']})", st["h2"]))
        head = ["Author", "Pub.", "Base", "Target", "Implied CAGR", "Method",
                "Independence"]
        rows = [head]
        for r in sorted(g["rows"], key=lambda x: x["target_value"]):
            rows.append([
                r["author"],
                str(r["published"])[:7],
                f"{r['base_year']}: {r['base_value']:,.0f}",
                f"{r['target_year']}: {r['target_value']:,.0f}",
                f"{r['implied_cagr']:.1%}",
                (r.get("method") or "not stated")[:28],
                ("restates " + r["upstream"]) if r.get("upstream") else "original",
            ])
        out.append(data_table(rows, [30 * mm, 14 * mm, 24 * mm, 24 * mm,
                                     18 * mm, 32 * mm, 28 * mm]))
        out.append(Spacer(1, 3))
        summary = (f"<b>Range:</b> {g['target_low']:,.0f} to "
                   f"{g['target_high']:,.0f} {g['unit']} "
                   f"({g['spread_ratio']:.2f}x high to low, median "
                   f"{g['target_median']:,.0f}). "
                   f"<b>Implied CAGR:</b> {g['cagr_low']:.1%} to "
                   f"{g['cagr_high']:.1%}. "
                   f"<b>Independence:</b> {g['count']} published estimates "
                   f"trace to {g['independent_count']} independent "
                   f"lineage{'s' if g['independent_count'] != 1 else ''}.")
        out.append(Paragraph(summary, st["body"]))
        if g["flags"]:
            out.append(Paragraph("<b>Flags raised on this set:</b>", st["h2"]))
            for f in g["flags"]:
                out.append(Paragraph(f"• {f}", st["note"]))
        out.append(Spacer(1, 5))
    return out


def forecast_scorecard(bundle, st) -> List[Any]:
    import estimate_core as ec
    outturns = bundle.get("outturns", [])
    if not outturns:
        return []
    scored = ec.score_forecasts(bundle.get("estimates", []), outturns)
    if not scored:
        return []
    out = [Paragraph("Past forecasts scored against outturn", st["h1"])]
    out.append(Paragraph(
        "A forecaster's record is knowable and is rarely reported. Where a "
        "forecast horizon has elapsed, it is scored here against what "
        "actually happened.", st["note"]))
    rows = [["Author", "Published", "Year", "Forecast", "Actual", "Error",
             "Verdict"]]
    for s in scored:
        rows.append([s["author"], str(s["published"])[:7], str(s["year"]),
                     f"{s['forecast']:,.0f}", f"{s['actual']:,.0f}",
                     f"{s['error']:+.1%}", s["verdict"]])
    out.append(data_table(rows, [34 * mm, 18 * mm, 14 * mm, 24 * mm, 24 * mm,
                                 20 * mm, 26 * mm]))
    out.append(Spacer(1, 6))
    return out


def methodology(bundle, st) -> List[Any]:
    phases = bundle.get("phases", {})
    if not phases:
        return []
    out = [Paragraph("How this was researched", st["h1"])]
    labels = [("scope", "Phase 1 — Scope"),
              ("disagreement", "Phase 2 — Mapping the disagreement"),
              ("deep_dive", "Phase 3 — Deep dive"),
              ("estimates", "Phase 4 — Estimate layer"),
              ("synthesis", "Phase 5 — Synthesis")]
    for key, label in labels:
        p = phases.get(key)
        if not p:
            continue
        out.append(Paragraph(label, st["h2"]))
        if isinstance(p, dict):
            if p.get("summary"):
                out.append(Paragraph(p["summary"], st["body"]))
            for q in p.get("sub_questions", []):
                out.append(Paragraph(f"• {q}", st["note"]))
            for item in p.get("items", []):
                out.append(Paragraph(f"• {item}", st["note"]))
        else:
            out.append(Paragraph(str(p), st["body"]))
    gaps = bundle.get("gaps", [])
    if gaps:
        out.append(Paragraph("What could not be established", st["h2"]))
        for g in gaps:
            out.append(Paragraph(f"• {g}", st["note"]))
    return out


def references(cites, st) -> List[Any]:
    out = [Paragraph("References", st["h1"])]
    out.append(Paragraph(
        "Numbered in order of first appearance in the text.", st["note"]))
    for n, s in cites.reference_list():
        bits = [f"<b>[{n}]</b>"]
        if s.get("author"):
            bits.append(f"{s['author']}.")
        bits.append(f"<i>{s.get('title', 'untitled')}</i>.")
        if s.get("publisher"):
            bits.append(f"{s['publisher']}.")
        if s.get("date"):
            bits.append(f"{s['date']}.")
        if s.get("kind"):
            bits.append(f"({s['kind']})")
        if s.get("url"):
            bits.append(f"<font color='#52514e'>{s['url']}</font>")
        if s.get("accessed"):
            bits.append(f"Accessed {s['accessed']}.")
        out.append(Paragraph(" ".join(bits), st["ref"]))
    return out


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def build(bundle: Dict[str, Any], out_path: str, chartdir: str = None) -> str:
    st = styles()
    cites = Citations(bundle.get("sources", []))
    meta = bundle["meta"]

    tmp = chartdir or tempfile.mkdtemp(prefix="financopedia_charts_")
    made = rc.render(bundle, tmp)
    rendered = {m["id"]: m["path"] for m in made}
    for i, c in enumerate(bundle.get("charts", []), start=1):
        c["_fignum"] = i

    story: List[Any] = []
    story.append(Paragraph(meta["title"], st["title"]))
    if meta.get("subtitle"):
        story.append(Paragraph(meta["subtitle"], st["subtitle"]))
    story.append(Paragraph(
        f"As of {meta['as_of']} · {meta.get('author', 'Financopedia')}"
        + (f" · {meta['coverage']}" if meta.get("coverage") else ""),
        st["meta"]))
    story.append(Spacer(1, 10))

    # the answer, first
    if bundle.get("answer"):
        story.append(Paragraph("The answer", st["h1"]))
        story.append(Paragraph(cites.render(bundle["answer"]), st["lead"]))

    story += key_findings(bundle, cites, st)

    # body sections, with charts placed where the bundle asks for them
    for sec in bundle.get("sections", []):
        story.append(Paragraph(sec["heading"], st["h1"]))
        if sec.get("confidence"):
            conf = sec["confidence"]
            hexval = "#" + CONFIDENCE.get(conf, INK_MUTED).hexval()[2:].rjust(6, "0")
            story.append(Paragraph(
                f"<font color='{hexval}'><b>Confidence: {conf}</b></font>",
                st["note"]))
        for para in sec.get("paragraphs", []):
            story.append(Paragraph(cites.render(para), st["body"]))
        for cid in sec.get("charts", []):
            chart = next((c for c in bundle["charts"] if c["id"] == cid), None)
            if chart:
                story += chart_block(chart, rendered, cites, st)
        for sub in sec.get("subsections", []):
            story.append(Paragraph(sub["heading"], st["h2"]))
            for para in sub.get("paragraphs", []):
                story.append(Paragraph(cites.render(para), st["body"]))
            for cid in sub.get("charts", []):
                chart = next((c for c in bundle["charts"] if c["id"] == cid), None)
                if chart:
                    story += chart_block(chart, rendered, cites, st)

    # any chart not explicitly placed still gets shown, so nothing is orphaned
    placed = {cid for sec in bundle.get("sections", [])
              for cid in sec.get("charts", [])}
    placed |= {cid for sec in bundle.get("sections", [])
               for sub in sec.get("subsections", [])
               for cid in sub.get("charts", [])}
    unplaced = [c for c in bundle.get("charts", []) if c["id"] not in placed]
    if unplaced:
        story.append(Paragraph("Additional exhibits", st["h1"]))
        for c in unplaced:
            story += chart_block(c, rendered, cites, st)

    story += estimate_table(bundle, cites, st)
    story += forecast_scorecard(bundle, st)
    story += methodology(bundle, st)
    story.append(PageBreak())
    story += references(cites, st)

    doc = make_doc(out_path, meta)
    doc.build(story)

    if cites.missing:
        print("WARNING: unresolved citation keys rendered as [?]: "
              + ", ".join(cites.missing), file=sys.stderr)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Build the research report PDF")
    ap.add_argument("bundle")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--chartdir", default=None)
    args = ap.parse_args()

    with open(args.bundle, "r", encoding="utf-8") as fh:
        bundle = json.load(fh)

    problems: List[str] = []
    rc.validate_charts(bundle, problems)
    import estimate_core as ec
    ec.validate(bundle.get("estimates", []), problems)
    if problems:
        print("bundle validation failed:")
        for p in problems:
            print(f"  - {p}")
        return 1

    out = args.out or f"research-{bundle['meta'].get('slug', 'report')}.pdf"
    build(bundle, out, args.chartdir)
    print(f"built {out}")
    print("  run audit_research.py before delivering this file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
