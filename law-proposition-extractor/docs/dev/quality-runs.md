# Quality runs

Large consolidated sources are split before frontier extraction (article headings when detectable, otherwise paragraph overlap). Prompt input size is estimated conservatively before each model call; if a chunk still cannot fit the configured limit, the run records `context_window_risk` and applies the case `extraction_fallback` policy (`fail_closed`, `mark_needs_review`, or heuristic fallback). A context-window risk is treated as a reviewable extraction failure, not a silent crash.

For staged equine passport operator commands and profile guidance, see [Equine passport staged runs](./equine-passport-staged-runs.md).
