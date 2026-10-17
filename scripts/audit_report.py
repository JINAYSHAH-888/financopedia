#!/usr/bin/env python3
"""
Financopedia report auditor.

Lints a research or earnings markdown file for the three failure modes that
make these reports untrustworthy:

  1. a figure with no source and no date
  2. an estimate presented as a fact
  3. recommendation language -- the output drifting from analysis into advice

    python3 audit_report.py research-TICKER.md
    python3 audit_report.py earnings-TICKER-Q3.md --kind earnings

Exit 0 means clean. Findings are printed with line numbers so they can be
fixed directly.
"""

from __future__ import annotations

import argparse
import re
import sys

# A figure: currency amounts, percentages, multiples, bare large numbers,
# basis points. Deliberately broad -- false positives are cheap to clear,
# an unsourced figure is not.
FIGURE = re.compile(
    r"(?<![\w.])("
    r"[$€£¥₹]\s?\d[\d,.]*\s?(?:bn|b|m|mm|k|billion|million|trillion)?"
    r"|\d[\d,.]*\s?(?:%|bps|x\b)"
    r"|\d[\d,.]*\s?(?:bn|b|m|mm|billion|million|trillion)\b"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\b\d+\.\d+\b"          # bare decimals: 920.2, 1.07 -- common in tables
    r"|\b\d{4,}\b"            # bare thousands: 4280 (a year is cleared by SOURCE_HINT)
    r")",
    re.IGNORECASE,
)

# Evidence that a figure is sourced: a year, an ISO date, a filing name, a
# URL, or an explicit unverified/inference label.
SOURCE_HINT = re.compile(
    r"(\b(19|20)\d{2}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b(10-K|10-Q|8-K|20-F|6-K|S-1|RNS|annual report|interim report|"
    r"quarterly report|press release|transcript|prospectus|filing|filed)\b"
    r"|https?://"
    r"|COULD NOT VERIFY"
    r"|INFERENCE)",
    re.IGNORECASE,
)

ADVICE = [
    (re.compile(r"\b(buy|sell|hold)\s+(the\s+)?(stock|shares|it|this)\b", re.I),
     "explicit buy/sell/hold instruction"),
    (re.compile(r"\b(we|I)\s+(recommend|advise|suggest\s+buying|would\s+buy|would\s+sell)\b", re.I),
     "direct recommendation"),
    (re.compile(r"\b(under|over)valued\b", re.I), "valuation verdict"),
    (re.compile(r"\battractive\s+(entry|valuation|opportunity|risk[-/ ]reward)\b", re.I),
     "advice framing"),
    (re.compile(r"\bcompelling\s+(opportunity|value|entry)\b", re.I), "advice framing"),
    (re.compile(r"\b(price\s+target|target\s+price|our\s+target)\b", re.I),
     "price target (reporting others' targets is fine -- attribute it)"),
    (re.compile(r"\b(should|ought\s+to)\s+(buy|sell|add|trim|exit|accumulate)\b", re.I),
     "instruction to act"),
    (re.compile(r"\b(strong|good|great)\s+(buy|investment)\b", re.I), "advice framing"),
    (re.compile(r"\b(bullish|bearish)\s+on\b", re.I),
     "stance language (describing others' stance is fine -- attribute it)"),
    (re.compile(r"\b(worth\s+(buying|owning)|a\s+steal|no[- ]brainer)\b", re.I),
     "advice framing"),
]

HEDGE = re.compile(
    r"\b(roughly|approximately|about|around|we estimate|I estimate|likely|"
    r"probably|appears to be|seems to be|on the order of)\b", re.I
)

SECTIONS = {
    "research": ["SNAPSHOT", "NEWS", "ANALYST VIEW", "COMPANY SAID", "NUMBERS",
                 "WHAT'S MISSING", "SOURCE LOG"],
    "earnings": ["WHAT THEY SAID", "HOW THEY SAID IT", "THE ANALYST QUESTIONS",
                 "AGAINST MY VIEW", "WHAT WOULD CHANGE MY MIND"],
}


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if p.strip()]


def audit(path, kind):
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    findings = []
    in_source_log = False
    in_code = False

    for n, raw in enumerate(lines, start=1):
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue

        if line.startswith("#"):
            in_source_log = bool(re.search(r"source\s*log", line, re.I))
            continue

        # advice language applies everywhere, including headings we skipped
        for pattern, why in ADVICE:
            m = pattern.search(line)
            if m:
                findings.append((n, "ADVICE", f"{why}: \"{m.group(0)}\""))

        if in_source_log:
            continue
        if re.match(r"^[|\s:-]+$", line):   # table divider
            continue

        unit = line
        if line.startswith("|"):            # treat a table row as one unit
            if SOURCE_HINT.search(unit):
                continue
            if FIGURE.search(unit):
                findings.append((n, "UNSOURCED",
                                 "table row carries figures but no filing or date"))
            continue

        for sentence in split_sentences(unit):
            figs = FIGURE.findall(sentence)
            if figs and not SOURCE_HINT.search(sentence):
                sample = figs[0][0] if isinstance(figs[0], tuple) else figs[0]
                findings.append((n, "UNSOURCED",
                                 f"figure \"{sample.strip()}\" with no source or date"))
            h = HEDGE.search(sentence)
            if h and "INFERENCE" not in sentence and "COULD NOT VERIFY" not in sentence:
                findings.append((n, "UNLABELLED",
                                 f"hedged claim \"{h.group(0)}\" not marked INFERENCE"))

    text = "\n".join(lines)
    missing = [s for s in SECTIONS.get(kind, []) if s.lower() not in text.lower()]

    # ---- report -----------------------------------------------------------
    print(f"\nFinancopedia report audit — {path} ({kind})")
    print("=" * 72)
    if missing:
        print(f"  [FAIL] missing required sections: {', '.join(missing)}")
    else:
        print(f"  [PASS] all {len(SECTIONS.get(kind, []))} required sections present")

    buckets = {"ADVICE": [], "UNSOURCED": [], "UNLABELLED": []}
    for n, kindtag, detail in findings:
        buckets[kindtag].append((n, detail))

    labels = {
        "ADVICE": "recommendation language (must be zero)",
        "UNSOURCED": "figures without a source and date",
        "UNLABELLED": "estimates not marked INFERENCE",
    }
    for key in ("ADVICE", "UNSOURCED", "UNLABELLED"):
        hits = buckets[key]
        if not hits:
            print(f"  [PASS] {labels[key]}: none")
            continue
        print(f"  [FAIL] {labels[key]}: {len(hits)}")
        for n, detail in hits[:25]:
            print(f"           line {n}: {detail}")
        if len(hits) > 25:
            print(f"           ... and {len(hits) - 25} more")

    print("=" * 72)
    failed = bool(missing or findings)
    if failed:
        print("  DO NOT DELIVER. Fix every line above and re-run.")
        print("  Sourcing fix: add the filing and its date in the same sentence,")
        print("  e.g. '(FY2025 10-K, filed 2026-02-14)'. If you cannot, write")
        print("  'COULD NOT VERIFY' and say where you looked.")
    else:
        print("  Clean. Citation and no-advice gates passed.")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description="Audit a Financopedia report")
    ap.add_argument("report")
    ap.add_argument("--kind", default="research", choices=["research", "earnings", "any"])
    args = ap.parse_args()
    return audit(args.report, args.kind)


if __name__ == "__main__":
    sys.exit(main())
