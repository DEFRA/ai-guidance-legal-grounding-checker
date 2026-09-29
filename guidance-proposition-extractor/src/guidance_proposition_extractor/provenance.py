"""Post-hoc provenance: section locators + soft verbatim checks.

Filled after the LLM emits propositions — not part of the tool schema.
``proposition_text`` is a derived rewrite for matching; ``source_paragraphs``
are the citation pin back to the page.
"""

from __future__ import annotations

from .adapters import all_paragraphs
from .fetch import FetchedPage
from .models import GuidanceProposition
from .scoring import _collapse, source_paragraph_verbatim


def attach_provenance(
    props: list[GuidanceProposition], page: FetchedPage
) -> tuple[list[GuidanceProposition], int]:
    """Attach ``section_locators``; return (props, n_verbatim_misses).

    A verbatim miss means one or more ``source_paragraphs`` are not a
    whitespace-collapsed substring of the page text (hallucination / paraphrase).
    Soft only — never fails the run.
    """
    paragraphs = all_paragraphs(page)
    n_misses = 0
    out: list[GuidanceProposition] = []
    for prop in props:
        if not source_paragraph_verbatim(prop.model_dump(), paragraphs):
            n_misses += 1
        locators: list[str] = []
        seen: set[str] = set()
        for src in prop.source_paragraphs:
            needle = _collapse(src)
            if not needle:
                continue
            for locator, paras in page.sections:
                if any(needle in _collapse(p) for p in paras):
                    if locator not in seen:
                        seen.add(locator)
                        locators.append(locator)
                    break
        out.append(prop.model_copy(update={"section_locators": locators}))
    return out, n_misses
