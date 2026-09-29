#!/usr/bin/env bash
set -euo pipefail

source_dir="docs/assets/infographics"
out_dir="docs/assets/generated/infographics"

mkdir -p "${out_dir}"
rm -f "${out_dir}"/*.svg "${out_dir}"/*.png

shopt -s nullglob
svg_sources=("${source_dir}"/*.svg)

if [[ ${#svg_sources[@]} -eq 0 ]]; then
  echo "No infographic SVG sources found under ${source_dir}" >&2
  exit 1
fi

if ! command -v rsvg-convert >/dev/null 2>&1; then
  echo "rsvg-convert not found (install with: brew install librsvg)" >&2
  echo "SVG copy will still proceed; PNG rasters will be skipped." >&2
  skip_png=1
else
  skip_png=0
fi

for src in "${svg_sources[@]}"; do
  name="$(basename "${src}" .svg)"
  out_svg="${out_dir}/${name}.svg"
  cp "${src}" "${out_svg}"
  echo "Copied ${out_svg}"

  if [[ "${skip_png}" -eq 0 ]]; then
    out_png="${out_dir}/${name}.png"
    rsvg-convert --width 1600 --keep-aspect-ratio --format=png "${src}" --output "${out_png}"
    echo "Rendered ${out_png}"
  fi
done
