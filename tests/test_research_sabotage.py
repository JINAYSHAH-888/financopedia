#!/usr/bin/env python3
"""Sabotage tests for the thematic research gates.

Each case breaks a research bundle in a way that still looks plausible, and
asserts the audit catches it. If one of these starts passing, the
corresponding gate has stopped working.

    python3 tests/test_research_sabotage.py
"""

import copy
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = os.path.join(ROOT, "templates", "bundle-thematic.json")
AUDIT = os.path.join(ROOT, "scripts", "audit_research.py")


def audit_passes(bundle):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(bundle, fh)
    fh.close()
    try:
        r = subprocess.run([sys.executable, AUDIT, fh.name],
                           capture_output=True, text=True)
        return r.returncode == 0
    finally:
        os.unlink(fh.name)


def dangling_citation(b):
    b["sections"][0]["paragraphs"][0] += " An extra claim [S:ghost-2026]."


def uncited_source(b):
    b["sources"].append({"key": "unused-2026", "title": "Never cited",
                         "date": "2026-01-01", "publisher": "X",
                         "url": "https://example.org/x"})


def uncited_figure(b):
    b["sections"][0]["paragraphs"].append(
        "Capacity utilisation averaged 34% across the fleet.")


def recommendation(b):
    b["sections"][1]["paragraphs"].append(
        "On balance the sector looks undervalued at current levels [S:bnef-2026].")


def estimate_without_author(b):
    del b["estimates"][0]["author"]


def phase_two_skipped(b):
    b["phases"]["disagreement"] = {"summary": "none found"}


def answer_buried(b):
    b["answer"] = " ".join(["word"] * 220) + " [S:iea-2026]"


def confidence_missing(b):
    b["key_findings"][0].pop("confidence", None)


def chart_series_mismatch(b):
    b["charts"][0]["series"][0]["values"] = [1, 2, 3]


def hedging_filler(b):
    b["sections"][0]["paragraphs"].append(
        "It is important to note that the landscape is complex [S:iea-2026].")


CASES = [
    ("a dangling citation key", dangling_citation),
    ("an uncited source padding the reference list", uncited_source),
    ("a figure in prose with no citation", uncited_figure),
    ("recommendation language", recommendation),
    ("an estimate with no author", estimate_without_author),
    ("the disagreement phase not actually run", phase_two_skipped),
    ("an answer longer than 150 words", answer_buried),
    ("a key finding with no confidence marker", confidence_missing),
    ("a chart series shorter than its x axis", chart_series_mismatch),
    ("hedging filler", hedging_filler),
]


def main():
    with open(BUNDLE, "r", encoding="utf-8") as fh:
        base = json.load(fh)

    if not audit_passes(base):
        print("  [ERROR] the clean example bundle does not pass its own audit")
        return 1
    print("  [ok] clean bundle passes")

    misses = []
    for desc, mutate in CASES:
        b = copy.deepcopy(base)
        mutate(b)
        if audit_passes(b):
            misses.append(desc)
            print(f"  [MISS] {desc}")
        else:
            print(f"  [caught] {desc}")

    print()
    if misses:
        print("Gates have regressed:")
        for m in misses:
            print(f"  NOT CAUGHT: {m}")
        return 1
    print(f"All {len(CASES)} research sabotage cases caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
