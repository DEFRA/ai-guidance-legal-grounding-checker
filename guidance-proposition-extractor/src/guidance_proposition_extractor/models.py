"""Proposition output schema."""

from pydantic import BaseModel, Field


class GuidanceProposition(BaseModel):
    """One atomic proposition lifted from a GOV.UK guidance page.

    ``proposition_text`` is a *derived* rewrite (atomic, self-contained) for
    matching and display — not a verbatim quote of the page.

    ``source_paragraphs`` are the citation pin: LLM-claimed verbatim
    paragraph/list-item text from the page. ``section_locators`` are filled
    post-hoc by matching those paragraphs to the fetched page structure
    (not emitted by the LLM tool schema).

    Metadata fields (subject_area, instrument, actor) carry the contextual
    grounding a downstream consumer needs to read the proposition in
    isolation. Empty values are legitimate — the prompt forbids guessing
    when the page doesn't supply the fact.
    """

    proposition_text: str
    subject_area: str = ""
    instrument: str = ""
    actor: str = ""
    source_paragraphs: list[str] = Field(default_factory=list)
    regulatory_kind: str = ""
    derives_from: list[str] = Field(default_factory=list)
    section_locators: list[str] = Field(default_factory=list)
