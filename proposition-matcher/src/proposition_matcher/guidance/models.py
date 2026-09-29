from pydantic import BaseModel


class GuidanceProposition(BaseModel):
    id: str
    section_locator: str
    proposition_text: str  # derived rewrite for matching — not a verbatim page quote
    legal_subject: str
    action: str = ""
    conditions: list[str] = []
    required_documents: list[str] = []
    source_url: str
    extraction_method: str  # "heuristic" | "llm" | "susan"
    source_paragraphs: list[str] = []  # verbatim page paragraphs (one per <p>/<li>) this proposition is drawn from
    content_id: str = ""  # gov.uk content id, threaded from Guidance Discovery/Guidance Relevance Filter/Guidance Proposition Extractor
    # ── group-rerank matching tag (from Guidance Proposition Extractor) ──
    regulatory_kind: str = ""  # statutory_obligation, permit_requirement, grant_condition,
                               # code_of_practice, procedural_step, factual_statement, definition
