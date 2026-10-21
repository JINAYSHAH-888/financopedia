#!/usr/bin/env bash
# Build every deliverable from its template and audit the result.
# Exits non-zero if any gate fails, so it works as a pre-commit or CI check.
set -uo pipefail

cd "$(dirname "$0")/.."
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

fail=0

# --- the four model types ------------------------------------------------
for t in dcf statements lbo ipo; do
  spec="templates/spec-$t.json"
  book="$OUT/model-$t.xlsx"

  if ! python3 scripts/build_model.py "$spec" --type "$t" -o "$book" >/dev/null; then
    echo "BUILD FAILED: $t"
    fail=1
    continue
  fi

  if python3 scripts/audit_model.py "$book" --spec "$spec" --type "$t" \
      > "$OUT/$t.log" 2>&1; then
    echo "$t: $(tail -1 "$OUT/$t.log" | xargs)"
  else
    echo "AUDIT FAILED: $t"
    cat "$OUT/$t.log"
    fail=1
  fi
done

# --- the thematic research report ----------------------------------------
REPORT="$OUT/research.pdf"
if python3 scripts/build_report.py templates/bundle-thematic.json \
     -o "$REPORT" --chartdir "$OUT/charts" >/dev/null 2>&1 \
   && python3 scripts/audit_research.py templates/bundle-thematic.json \
     --pdf "$REPORT" > "$OUT/research.log" 2>&1; then
  echo "research: $(tail -1 "$OUT/research.log" | xargs)"
else
  echo "RESEARCH REPORT FAILED"
  cat "$OUT/research.log" 2>/dev/null
  fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "Everything built and passed its audit."
else
  echo "Something failed above. Do not ship output that has not passed."
fi
exit "$fail"
