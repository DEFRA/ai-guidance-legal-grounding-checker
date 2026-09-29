#!/usr/bin/env bash
# Build the full guidance corpus: stage 1 (discover) then stage 2 (fetch bodies).
# Uses default paths from config.py: output/search_api.json -> output/with_body.json
set -euo pipefail
cd "$(dirname "$0")"
uv run python src/get_defra_guidance_pages.py
uv run python src/fetch_body.py
