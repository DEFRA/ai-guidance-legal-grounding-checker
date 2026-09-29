#!/usr/bin/env bash
# Dev/demo: export the Article 109 equine pilot into the operations bundle directory
# (same default as the API: dist/static-report). Uses a fresh derived-artifacts cache
# per run so proposition extraction is not served from stale cache.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="${OPERATIONS_EXPORT_DIR:-dist/static-report}"
_TMP="${TMPDIR:-/tmp}"
_TMP="${_TMP%/}"
DERIVED="$(mktemp -d "${_TMP}/lpe-derived-art109-XXXXXX")"
cleanup() {
  rm -rf "$DERIVED"
}
trap cleanup EXIT

echo "Exporting examples/pilot_reg_2016_429_art109_equine.json"
echo "  output:    $OUT"
echo "  derived:   $DERIVED (ephemeral, discarded after export)"
echo ""

uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline export-case \
  examples/pilot_reg_2016_429_art109_equine.json \
  --output-dir "$OUT" \
  --derived-cache-dir "$DERIVED"

WEB="${JUDIT_WEB_ORIGIN:-http://localhost:3000}"
WEB="${WEB%/}"

echo ""
echo "Propositions (equine filter): ${WEB}/propositions?scope=equine"
echo "Match the API bundle path:    export OPERATIONS_EXPORT_DIR=$OUT"
echo "  (pydantic env: OPERATIONS_EXPORT_DIR — same variable this script uses by default.)"
echo ""
echo "Example proposition: Art 109 §1(d)(i) with equine direct/high scope link; use review"
