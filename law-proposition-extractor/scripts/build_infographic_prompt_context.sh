#!/usr/bin/env bash
set -euo pipefail

out_dir="docs/assets/generated/context"
out_file="${out_dir}/infographic-prompt-context.md"
legacy_out_file="docs/assets/generated/infographic-prompt-context.md"

mkdir -p "${out_dir}"
rm -f "${legacy_out_file}"

canonical_files=(
  "docs/canonical/project-state.md"
  "docs/canonical/roadmap.md"
  "docs/canonical/audiences.md"
  "docs/canonical/visuals.md"
)

for file in "${canonical_files[@]}"; do
  if [[ ! -f "${file}" ]]; then
    echo "Error: missing canonical source file: ${file}" >&2
    exit 1
  fi
done

{
  echo "# Law Proposition Extractor infographic prompt context"
  echo
  echo "This file is generated from canonical state docs for prompt authoring."
  echo "Do not edit manually."
  echo
  for file in "${canonical_files[@]}"; do
    echo "## ${file}"
    echo
    cat "${file}"
    echo
  done
} > "${out_file}"

echo "Wrote ${out_file}"
