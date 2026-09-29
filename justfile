# Repo-level tasks for ai-eu-trade-accelerator (Guidance to Law Comparison).
# Component-local tasks (e.g. LPE assets) stay under law-proposition-extractor/justfile.

# Regenerate committed SVG + PNG companions from docs/diagrams/**/*.d2 (excludes shared/).
diagrams:
    ./scripts/render_diagrams.sh
