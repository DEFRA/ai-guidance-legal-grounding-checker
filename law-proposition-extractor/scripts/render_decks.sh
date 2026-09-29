#!/usr/bin/env bash
set -euo pipefail

source_dir="docs/assets/decks"
out_dir="docs/assets/generated/decks"

mkdir -p "${out_dir}"
rm -f "${out_dir}"/*.html "${out_dir}"/*.pdf "${out_dir}"/*.pptx
rm -f docs/assets/generated/*.html docs/assets/generated/*.pdf docs/assets/generated/*.pptx

shopt -s nullglob
deck_files=("${source_dir}"/*.md)

if [[ ${#deck_files[@]} -eq 0 ]]; then
  echo "No deck sources found under ${source_dir}" >&2
  exit 1
fi

rendered=0

for deck in "${deck_files[@]}"; do
  if [[ "$(basename "${deck}")" == "README.md" ]]; then
    continue
  fi

  name="$(basename "${deck}" .md)"

  npx marp "${deck}" \
    --no-stdin \
    --allow-local-files \
    --html \
    --output "${out_dir}/${name}.html"

  npx marp "${deck}" \
    --no-stdin \
    --allow-local-files \
    --pdf \
    --output "${out_dir}/${name}.pdf"

  npx marp "${deck}" \
    --no-stdin \
    --allow-local-files \
    --pptx \
    --output "${out_dir}/${name}.pptx"

  echo "Rendered ${name} deck artifacts"
  rendered=$((rendered + 1))
done

if [[ ${rendered} -eq 0 ]]; then
  echo "No renderable deck markdown files found in ${source_dir}" >&2
  exit 1
fi