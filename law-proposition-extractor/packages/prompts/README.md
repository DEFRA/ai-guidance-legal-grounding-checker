# Law Proposition Extractor prompt assets

This directory holds versioned prompt templates and prompt fixtures used by
controlled LLM stages (primarily proposition extraction).

Current layout is package-local rather than a deep subdirectory tree. Prefer the
versioned prompt assets referenced by extraction configuration and run traces
(`prompt_version`, model alias) over inventing parallel copies.

Do not treat prompt text as DecisionExplanation content: explanations record
deterministic processing decisions, not model chain-of-thought.
