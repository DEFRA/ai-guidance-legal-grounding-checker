"""Render a fetched page into the structured-adapter body the prompt expects.

Guidance Proposition Extractor only ships the structured adapter — flat-body extraction lost the
pairwise contest.
"""

from .fetch import FetchedPage


def render_structured_body(page: FetchedPage) -> str:
    """Each section prefixed with its [locator], paragraphs preserved."""
    chunks: list[str] = []
    for locator, paragraphs in page.sections:
        section_body = "\n".join(paragraphs)
        chunks.append(f"[{locator}]\n{section_body}")
    return "\n\n".join(chunks)


def all_paragraphs(page: FetchedPage) -> list[str]:
    """Flat list of every paragraph/list-item across the page."""
    return [p for _, paras in page.sections for p in paras]
