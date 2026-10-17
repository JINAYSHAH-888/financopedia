#!/usr/bin/env python3
"""Checks that never fail prove nothing.

Each case below breaks a model in a way that produces a plausible-looking
workbook, and asserts the audit catches it. If one of these ever passes, the
corresponding gate has stopped working.

    python3 tests/test_sabotage.py
"""

import os
import subprocess
import sys
import tempfile

from openpyxl import load_workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def build(model_type, out):
    spec = os.path.join(ROOT, "templates", f"spec-{model_type}.json")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_model.py"),
                    spec, "--type", model_type, "-o", out],
                   check=True, capture_output=True)
    return spec


def audit_passes(book, spec, model_type):
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "scripts", "audit_model.py"),
                        book, "--spec", spec, "--type", model_type],
                       capture_output=True, text=True)
    return r.returncode == 0


# (model type, description, mutation)
CASES = [
    ("dcf", "hardcoded value in the projection",
     lambda wb: wb["PROJECTION"].__setitem__("D4", 9999.0)),
    ("dcf", "terminal value formula missing its (1+g)",
     lambda wb: wb["VALUATION"].__setitem__(
         "B10", "=H4/(INPUTS!$B$10-INPUTS!$B$11)")),
    ("dcf", "beta re-levered without the tax shield",
     lambda wb: wb["WACC"].__setitem__("B40", "=H10*(1+B38)")),
    ("dcf", "index regressed on the stock instead of the reverse",
     lambda wb: wb["BETA_REGRESSION"].__setitem__(
         "H5", "=SLOPE(E5:E123,C5:C123)")),
    ("statements", "a line dropped from the balance sheet total",
     lambda wb: wb["BALANCE"].__setitem__("B19", "=SUM(B12:B18)-B13")),
    ("lbo", "interest charged on closing rather than opening balances",
     lambda wb: wb["DEBT"].__setitem__("C9", "=C8*INPUTS!$C$25")),
    ("ipo", "net debt not deducted in the EV/EBITDA method",
     lambda wb: wb["VALUATION"].__setitem__("B12", "=B8*B5")),
]


def main():
    tmp = tempfile.mkdtemp()
    failures = []
    for model_type, desc, mutate in CASES:
        clean = os.path.join(tmp, f"{model_type}-clean.xlsx")
        spec = build(model_type, clean)
        broken = os.path.join(tmp, f"{model_type}-broken.xlsx")
        wb = load_workbook(clean)
        mutate(wb)
        wb.save(broken)

        if audit_passes(broken, spec, model_type):
            failures.append(f"{model_type}: NOT CAUGHT — {desc}")
            print(f"  [MISS] {model_type}: {desc}")
        else:
            print(f"  [caught] {model_type}: {desc}")

    print()
    if failures:
        print("Gates have regressed:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"All {len(CASES)} sabotage cases caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
