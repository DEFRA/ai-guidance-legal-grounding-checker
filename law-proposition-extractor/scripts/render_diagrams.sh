#!/usr/bin/env bash
set -euo pipefail

source_dir="docs/assets/diagrams"
out_dir="docs/assets/generated/diagrams"

mkdir -p "${out_dir}"
rm -f "${out_dir}"/*.svg
rm -f docs/assets/generated/*.svg

shopt -s nullglob
diagram_files=("${source_dir}"/*.d2)

if [[ ${#diagram_files[@]} -eq 0 ]]; then
  echo "No diagram sources found under ${source_dir}" >&2
  exit 1
fi

for diagram in "${diagram_files[@]}"; do
  name="$(basename "${diagram}" .d2)"
  output="${out_dir}/${name}.svg"
  d2 "${diagram}" "${output}"
  echo "Rendered ${output}"
done