#!/usr/bin/env bash
# Render repo-level D2 diagrams under docs/diagrams/ → docs/diagrams/generated/
# Emits both SVG (docs/repo render) and PNG (portable/shareable companion).
# Usage: from repository root — just diagrams  |  ./scripts/render_diagrams.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${root}"

source_root="docs/diagrams"
out_root="docs/diagrams/generated"

# Shared render options (same layout/theme/pad for SVG and PNG).
# PNG --scale=1: D2's Playwright export already applies a 2× device-pixel ratio,
# so this yields ~2× the SVG logical size — readable in Slack without multi‑MB
# 4× rasters. Do not post-resize the PNG.
theme=0
pad=100
png_scale=1

if ! command -v d2 >/dev/null 2>&1; then
  echo "error: d2 is not installed or not on PATH." >&2
  echo "Install with: brew install d2" >&2
  exit 1
fi

if [[ ! -d "${source_root}" ]]; then
  echo "error: missing ${source_root}" >&2
  exit 1
fi

# Clear previous generated renders only (leave other assets alone if added later).
if [[ -d "${out_root}" ]]; then
  find "${out_root}" -type f \( -name '*.svg' -o -name '*.png' \) -delete
fi

png_hint() {
  cat >&2 <<'EOF'
error: D2 PNG export failed (Playwright / browser deps missing or broken).

D2 renders PNG via Playwright (playwright-go). This is developer tooling only —
nothing is added to application package dependencies.

Resolve, then re-run `just diagrams`:

  1. Ensure Chromium for Playwright is installed (user cache):

       unset PLAYWRIGHT_BROWSERS_PATH
       npx --yes playwright install chromium

     Linux (missing OS libraries):

       npx --yes playwright install --with-deps chromium

  2. If d2 still reports 404 downloading playwright-*-*.zip, the legacy
     Playwright driver CDN is gone for the version pinned by your d2 build.
     Seed the playwright-go driver cache (macOS arm64 / d2 0.7.x example):

       CACHE="$HOME/Library/Caches/ms-playwright-go/1.47.2"
       mkdir -p "$CACHE"
       curl -fsSL -o /tmp/pw-driver.zip \
         'https://cdn.playwright.dev/dbazure/download/playwright/builds/driver/playwright-1.50.1-mac-arm64.zip'
       unzip -oq /tmp/pw-driver.zip -d "$CACHE"
       chmod +x "$CACHE/node"
       # playwright-go checks package version == cache folder name:
       python3 -c "import json,pathlib; p=pathlib.Path('$CACHE/package/package.json'); d=json.loads(p.read_text()); d['version']='1.47.2'; p.write_text(json.dumps(d,indent=2)+'\n')"
       unset PLAYWRIGHT_BROWSERS_PATH
       "$CACHE/node" "$CACHE/package/cli.js" install chromium

PNG companions are required for `just diagrams`; SVG-only success is not enough.
EOF
}

count=0
while IFS= read -r diagram; do
  [[ -z "${diagram}" ]] && continue
  rel="${diagram#"${source_root}/"}"
  name="${rel%.d2}"
  out_svg="${out_root}/${name}.svg"
  out_png="${out_root}/${name}.png"
  mkdir -p "$(dirname "${out_svg}")"

  # Architecture and concept views prefer ELK (narrower); pipeline stays on dagre.
  layout="dagre"
  diagram_pad="${pad}"
  extra_flags=()
  case "${diagram}" in
    */architecture/*|*/concepts/*) layout="elk" ;;
  esac
  # C1: near-positioned people/externals need generous pad + ELK layer gaps
  # so horizontal supply/inference edges do not crowd labels.
  # C1/C2: near-positioned people/externals need controlled outer pad;
  # inter-group corridors come from diagram structure (centre frame / boundary).
  case "${diagram}" in
    */architecture/c1-*)
      # Outer pad only — inter-group corridors come from the transparent centre frame.
      # 140 maximises content in the PNG without crowding connector labels.
      diagram_pad=140
      extra_flags=(
        --elk-nodeNodeBetweenLayers=180
        --elk-edgeNodeBetweenLayers=100
        --elk-padding='[top=40,left=40,bottom=40,right=40]'
      )
      ;;
    */architecture/c2-*)
      diagram_pad=140
      extra_flags=(
        --elk-nodeNodeBetweenLayers=100
        --elk-edgeNodeBetweenLayers=60
        --elk-padding='[top=40,left=40,bottom=40,right=40]'
      )
      ;;
  esac

  common=(--layout="${layout}" --theme="${theme}" --pad="${diagram_pad}" "${extra_flags[@]}")

  d2 "${common[@]}" "${diagram}" "${out_svg}"
  echo "Rendered ${out_svg} (layout=${layout})"

  # PNG must succeed — do not silently skip while reporting success.
  if ! d2 "${common[@]}" --scale="${png_scale}" "${diagram}" "${out_png}"; then
    png_hint
    exit 1
  fi
  echo "Rendered ${out_png} (layout=${layout}, scale=${png_scale})"

  count=$((count + 1))
done < <(
  find "${source_root}" \
    -type f \
    -name '*.d2' \
    ! -path "${source_root}/generated/*" \
    ! -path "${source_root}/shared/*" \
    | sort
)

if [[ "${count}" -eq 0 ]]; then
  echo "No diagram sources found under ${source_root} (excluding shared/ and generated/)." >&2
  exit 1
fi

echo "Done: ${count} diagram(s) → SVG + PNG under ${out_root}/"
