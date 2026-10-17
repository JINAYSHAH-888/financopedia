#!/usr/bin/env bash
# Build every model type from its template spec and audit the result.
# Exits non-zero if any gate fails, so it works as a pre-commit or CI check.
set -uo pipefail

cd "$(dirname "$0")/.."
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

fail=0
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

echo
if [ "$fail" -eq 0 ]; then
  echo "All model types built and passed their audits."
else
  echo "Something failed above. Do not ship a workbook that has not passed."
fi
exit "$fail"
