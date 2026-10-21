#!/usr/bin/env python3
"""
The gate for a thematic research report.

Same contract as the model auditors: mechanical checks, fixed rather than
explained away, exit 0 or the report does not ship. What it proves here is
provenance and discipline rather than arithmetic —

* every citation marker resolves to a real source, and every source is cited;
* every figure in prose sits in a sentence that carries a marker;
* every published estimate has full provenance and the spread is disclosed;
* every chart's data is in the bundle and every chart is cited;
* the phases actually ran, with their gates met;
* nothing in the report tells the reader what to do.

    python3 audit_research.py bundle.json --pdf research-topic.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estimate_core as ec  # noqa: E402
import research_charts as rc  # noqa: E402
from audit_lib import Audit  # noqa: E402
from build_report import CITE, cite_keys  # noqa: E402

# A figure: currency, percentages, multiples, bare large numbers, basis points.
FIGURE = re.compile(
    r"(?<![\w.])("
    r"[$€£¥₹]\s?\d[\d,.]*\s?(?:bn|b|m|mm|k|billion|million|trillion|cr|crore|lakh)?"
    r"|\d[\d,.]*\s?(?:%|bps|x\b)"
    r"|\d[\d,.]*\s?(?:bn|b|m|mm|billion|million|trillion|cr|crore|lakh)\b"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\b\d+\.\d+\b"
    r")", re.IGNORECASE)

ADVICE = [
    (re.compile(r"\b(buy|sell|hold)\s+(the\s+)?(stock|shares|it|this|sector)\b", re.I),
     "explicit buy/sell/hold instruction"),
    (re.compile(r"\b(we|I)\s+(recommend|advise|suggest\s+buying|would\s+buy|would\s+sell)\b", re.I),
     "direct recommendation"),
    (re.compile(r"\b(under|over)valued\b", re.I), "valuation verdict"),
    (re.compile(r"\battractive\s+(entry|valuation|opportunity|risk[-/ ]reward)\b", re.I),
     "advice framing"),
    (re.compile(r"\bcompelling\s+(opportunity|value|entry|investment)\b", re.I),
     "advice framing"),
    (re.compile(r"\b(price\s+target|target\s+price|our\s+target)\b", re.I),
     "price target (reporting others' is fine — attribute it)"),
    (re.compile(r"\b(should|ought\s+to)\s+(buy|sell|invest|allocate|exit|accumulate)\b", re.I),
     "instruction to act"),
    (re.compile(r"\binvestors\s+should\b", re.I), "instruction to act"),
    (re.compile(r"\b(bullish|bearish)\s+on\b", re.I),
     "stance language (describing others' stance is fine — attribute it)"),
    (re.compile(r"\b(worth\s+(buying|owning)|a\s+steal|no[- ]brainer)\b", re.I),
     "advice framing"),
]

FILLER = re.compile(
    r"\b(it is important to note|it should be noted|the landscape is complex"
    r"|various factors|a number of factors|needless to say|it goes without saying"
    r"|in today's (fast[- ]paced|ever[- ]changing))\b", re.I)

CONFIDENCES = {"well-evidenced", "contested", "thin"}


def all_prose(bundle: Dict[str, Any]) -> List[tuple]:
    """Every piece of body prose, tagged with where it came from."""
    out = []
    if bundle.get("answer"):
        out.append(("answer", bundle["answer"]))
    for f in bundle.get("key_findings", []):
        out.append(("key finding", f.get("text", "")))
    for sec in bundle.get("sections", []):
        for p in sec.get("paragraphs", []):
            out.append((f"section '{sec['heading']}'", p))
        for sub in sec.get("subsections", []):
            for p in sub.get("paragraphs", []):
                out.append((f"subsection '{sub['heading']}'", p))
    return out


def split_sentences(text: str) -> List[str]:
    stripped = CITE.sub(" ", text)
    parts = re.split(r"(?<=[.!?])\s+", stripped)
    raw = re.split(r"(?<=[.!?])\s+", text)
    # pair each cleaned sentence with its original, so citation markers in the
    # original can be tested against figures in the cleaned text
    return list(zip(parts, raw + [""] * (len(parts) - len(raw))))


def audit(bundle_path: str, pdf_path: str = None) -> Audit:
    a = Audit("Financopedia research audit")
    with open(bundle_path, "r", encoding="utf-8") as fh:
        bundle = json.load(fh)

    # ---- 1. structure -----------------------------------------------------
    for key in ("meta", "answer", "key_findings", "sections", "sources"):
        if not bundle.get(key):
            a.check(f"Bundle has {key}", False, "required")
    for key in ("title", "as_of", "slug"):
        if not bundle.get("meta", {}).get(key):
            a.check(f"meta.{key} present", False, "required")
    if a.failures:
        return a
    a.check("Bundle structure complete", True,
            "meta, answer, key findings, sections, sources")

    # ---- 2. citations resolve, and every source is used -------------------
    source_keys = {s["key"] for s in bundle["sources"]}
    missing_meta = [s.get("key", "?") for s in bundle["sources"]
                    if not (s.get("title") and s.get("date"))]
    a.check("Every source has a title and a date", not missing_meta,
            f"incomplete: {missing_meta[:5]}" if missing_meta
            else f"{len(source_keys)} sources")

    used, dangling = set(), []
    for where, text in all_prose(bundle):
        for m in CITE.finditer(text):
            for k in cite_keys(m.group(1)):
                if k in source_keys:
                    used.add(k)
                else:
                    dangling.append(f"{where}: [S:{k}]")
    for c in bundle.get("charts", []):
        for k in c.get("cites", []):
            if k in source_keys:
                used.add(k)
            else:
                dangling.append(f"chart {c.get('id')}: [S:{k}]")

    a.check("Every citation marker resolves to a source", not dangling,
            f"{len(dangling)} dangling: {dangling[:4]}" if dangling
            else f"{len(used)} sources cited")

    orphans = sorted(source_keys - used)
    a.check("Every source in the list is cited at least once", not orphans,
            f"uncited: {orphans[:6]} — cite them or remove them" if orphans
            else "no padding in the reference list")

    # ---- 3. every figure in prose is in a cited sentence ------------------
    unsourced = []
    for where, text in all_prose(bundle):
        for clean, original in split_sentences(text):
            if not clean.strip():
                continue
            figs = FIGURE.findall(clean)
            if figs and not CITE.search(original or ""):
                sample = figs[0][0] if isinstance(figs[0], tuple) else figs[0]
                unsourced.append(f"{where}: \"{str(sample).strip()}\"")
    a.check("Every figure in prose sits in a cited sentence", not unsourced,
            f"{len(unsourced)} uncited figures: {unsourced[:4]}" if unsourced
            else "all figures carry a marker")

    # ---- 4. no advice, no filler -----------------------------------------
    advice_hits, filler_hits = [], []
    for where, text in all_prose(bundle):
        for pattern, why in ADVICE:
            m = pattern.search(text)
            if m:
                advice_hits.append(f"{where}: {why} — \"{m.group(0)}\"")
        m = FILLER.search(text)
        if m:
            filler_hits.append(f"{where}: \"{m.group(0)}\"")
    a.check("No recommendation language", not advice_hits,
            "; ".join(advice_hits[:3]) if advice_hits
            else "report-and-analyse only")
    a.check("No hedging filler", not filler_hits,
            "; ".join(filler_hits[:3]) if filler_hits
            else "no 'it is important to note'")

    # ---- 5. the answer comes first and is short --------------------------
    words = len(re.sub(r"\[S:[^\]]+\]", "", bundle["answer"]).split())
    a.check("The answer is stated in the first 150 words",
            0 < words <= 150, f"{words} words — the conclusion must be readable "
            "before the evidence")

    # ---- 6. confidence marked per finding and section --------------------
    bad_conf = [f.get("text", "")[:40] for f in bundle["key_findings"]
                if f.get("confidence") not in CONFIDENCES]
    a.check("Every key finding carries a confidence marker", not bad_conf,
            f"missing or invalid on: {bad_conf[:3]}" if bad_conf
            else f"{len(bundle['key_findings'])} findings, all marked")
    sec_conf = [s["heading"] for s in bundle["sections"]
                if s.get("confidence") not in CONFIDENCES]
    a.check("Every section carries a confidence marker", not sec_conf,
            f"missing on: {sec_conf[:4]}" if sec_conf
            else f"{len(bundle['sections'])} sections, all marked")
    levels = {f.get("confidence") for f in bundle["key_findings"]}
    if len(levels) == 1 and len(bundle["key_findings"]) > 2:
        a.info("Confidence spread",
               f"every finding is '{levels.pop()}' — uniform confidence tells "
               "the reader nothing about reliability; check it is honest")

    # ---- 7. the phases ran -----------------------------------------------
    phases = bundle.get("phases", {})
    needed = ["scope", "disagreement", "deep_dive", "estimates", "synthesis"]
    absent = [p for p in needed if not phases.get(p)]
    a.check("All five phases recorded", not absent,
            f"missing: {absent}" if absent else "scope → disagreement → "
            "deep dive → estimates → synthesis")

    scope = phases.get("scope") or {}
    subs = scope.get("sub_questions", [])
    a.check("Phase 1 gate: question decomposed into 4–8 sub-questions",
            4 <= len(subs) <= 8, f"{len(subs)} sub-questions")

    dis = phases.get("disagreement") or {}
    items = dis.get("items", [])
    a.check("Phase 2 gate: disagreements identified or consensus evidenced",
            len(items) >= 2 or bool(dis.get("consensus_evidence")),
            f"{len(items)} disagreement(s) mapped" if items
            else "consensus claim evidenced"
            if dis.get("consensus_evidence") else
            "a report finding no disagreement anywhere has usually not looked")

    # ---- 8. estimates ----------------------------------------------------
    problems: List[str] = []
    ec.validate(bundle.get("estimates", []), problems)
    a.check("Every estimate has full provenance", not problems,
            "; ".join(problems[:3]) if problems
            else f"{len(bundle.get('estimates', []))} estimates, "
            "author/date/base/target/source all present")

    if bundle.get("estimates"):
        groups = ec.analyse_bundle(bundle)
        for subj, g in groups.items():
            a.info(f"Estimate spread — {subj}",
                   f"{g['target_low']:,.0f}–{g['target_high']:,.0f} {g['unit']} "
                   f"({g['spread_ratio']:.2f}x), {g['count']} estimates from "
                   f"{g['independent_count']} independent lineage(s)")
            if g["independent_count"] == 1 and g["count"] > 1:
                a.info("Independence warning",
                       f"all {g['count']} estimates for '{subj}' trace to one "
                       "source — this is one data point, not corroboration")
        # the spread has to be disclosed in the prose, not just tabulated
        prose = " ".join(t for _, t in all_prose(bundle)).lower()
        mentions = any(w in prose for w in ("spread", "range", "x high to low",
                                            "diverge", "disagree"))
        a.check("The estimate spread is discussed in the body", mentions,
                "the comparison table alone is not enough — the body must say "
                "what the disagreement is" if not mentions
                else "spread addressed in prose")

    # ---- 9. charts -------------------------------------------------------
    chart_problems: List[str] = []
    rc.validate_charts(bundle, chart_problems)
    a.check("Every chart validates and carries its data", not chart_problems,
            "; ".join(chart_problems[:3]) if chart_problems
            else f"{len(bundle.get('charts', []))} charts, series complete")

    if bundle.get("charts"):
        placed = {cid for s in bundle["sections"] for cid in s.get("charts", [])}
        placed |= {cid for s in bundle["sections"]
                   for sub in s.get("subsections", [])
                   for cid in sub.get("charts", [])}
        a.info("Chart placement",
               f"{len(placed)} of {len(bundle['charts'])} placed in sections; "
               "any remainder is appended as additional exhibits")

    # ---- 10. the PDF actually came out -----------------------------------
    if pdf_path:
        exists = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 20_000
        a.check("PDF produced", exists,
                f"{os.path.getsize(pdf_path):,} bytes" if os.path.exists(pdf_path)
                else "not found")
        if exists:
            try:
                from pypdf import PdfReader
                pages = len(PdfReader(pdf_path).pages)
                a.info("PDF length", f"{pages} pages")
            except Exception:
                pass
    return a


def main():
    ap = argparse.ArgumentParser(description="Audit a thematic research report")
    ap.add_argument("bundle")
    ap.add_argument("--pdf", default=None)
    args = ap.parse_args()
    return audit(args.bundle, args.pdf).report()


if __name__ == "__main__":
    sys.exit(main())
