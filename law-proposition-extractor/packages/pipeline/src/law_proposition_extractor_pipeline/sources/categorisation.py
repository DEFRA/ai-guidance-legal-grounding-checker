import re
from typing import Any

from law_proposition_extractor_domain import SourceCategorisationRationale, SourceTargetLink

SOURCE_ROLES = {
    "base_act",
    "amendment",
    "delegated_act",
    "implementing_act",
    "guidance",
    "explanatory_material",
    "certificate_model",
    "annex",
    "corrigendum",
    "case_file",
    "unknown",
}

RELATIONSHIPS = {
    "analysis_target",
    "modifies_target",
    "implements_target",
    "explains_target",
    "evidences_target",
    "contextual_source",
    "unknown",
}

TARGET_LINK_TYPES = {
    "is_target",
    "amends",
    "implements",
    "supplements",
    "corrects",
    "explains",
    "evidences",
    "contains_annex_to",
    "references",
    "contextual",
    "unknown",
}

LINK_TO_RELATIONSHIP = {
    "is_target": "analysis_target",
    "amends": "modifies_target",
    "corrects": "modifies_target",
    "implements": "implements_target",
    "supplements": "implements_target",
    "explains": "explains_target",
    "evidences": "evidences_target",
    "contains_annex_to": "contextual_source",
    "references": "contextual_source",
    "contextual": "contextual_source",
    "unknown": "unknown",
}


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _lower_text(value: Any) -> str:
    return _to_text(value).lower()


def _truthy_signal(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return False


def _tokens_from_source(source: Any) -> dict[str, str]:
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    title = _to_text(source.title)
    citation = _to_text(source.citation)
    kind = _to_text(source.kind)
    url = _to_text(source.source_url)
    authority = _to_text(metadata.get("authority") or source.provenance or "")
    instrument_id = _to_text(metadata.get("instrument_id") or metadata.get("authority_source_id") or "")
    text_parts = [
        title,
        citation,
        kind,
        url,
        authority,
        instrument_id,
        _to_text(metadata.get("long_title")),
        _to_text(metadata.get("document_type")),
        _to_text(metadata.get("document_subtype")),
    ]
    searchable_text = " | ".join(part for part in text_parts if part)
    return {
        "title": title,
        "citation": citation,
        "kind": kind,
        "url": url,
        "authority": authority,
        "instrument_id": instrument_id,
        "searchable_text": searchable_text,
        "searchable_text_lower": searchable_text.lower(),
    }


def _target_linked(source: Any, *, primary_target_citation: str | None) -> bool:
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    if _truthy_signal(metadata.get("is_target_source")):
        return True
    target_citation = _to_text(metadata.get("target_citation"))
    source_citation = _to_text(source.citation)
    if target_citation and source_citation and target_citation.lower() == source_citation.lower():
        return True
    target_citations = metadata.get("target_citations")
    if isinstance(target_citations, list):
        normalized = {_lower_text(item) for item in target_citations if _to_text(item)}
        if source_citation and source_citation.lower() in normalized:
            return True
    if primary_target_citation and source_citation:
        return primary_target_citation.lower() == source_citation.lower()
    return False


def _contains(value: str, pattern: str) -> bool:
    return bool(re.search(pattern, value, flags=re.IGNORECASE))


def _primary_target_matches(source: Any, *, primary_target_source_id: str | None) -> bool:
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    if _truthy_signal(metadata.get("is_target_source")):
        return True
    return bool(primary_target_source_id and str(source.id) == primary_target_source_id)


def _mentions_target(
    *,
    searchable_text: str,
    target_citation: str | None,
    target_instrument_id: str | None,
    target_title: str | None,
) -> bool:
    normalized = searchable_text.lower()
    candidates = [
        _lower_text(target_citation),
        _lower_text(target_instrument_id),
        _lower_text(target_title),
    ]
    return any(candidate and candidate in normalized for candidate in candidates)


def _citation_family(value: str | None) -> str:
    citation = _lower_text(value)
    if not citation:
        return ""
    if "-" in citation:
        return citation.split("-", maxsplit=1)[0]
    if "/" in citation:
        return citation.split("/", maxsplit=1)[0]
    return citation.split(" ", maxsplit=1)[0]


def build_source_target_link(
    *,
    source: Any,
    primary_target_source_id: str | None,
    primary_target_citation: str | None,
    primary_target_instrument_id: str | None,
    primary_target_title: str | None,
) -> SourceTargetLink:
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    source_record_id = str(source.id)
    tokens = _tokens_from_source(source)
    searchable_text = tokens["searchable_text_lower"]
    target_linked = _mentions_target(
        searchable_text=searchable_text,
        target_citation=primary_target_citation,
        target_instrument_id=primary_target_instrument_id,
        target_title=primary_target_title,
    )
    target_source_record_id = primary_target_source_id
    target_citation = primary_target_citation
    target_instrument_id = primary_target_instrument_id

    link_type = "unknown"
    confidence = "low"
    method = "fallback"
    reason = "No deterministic target-link rule matched."
    evidence: list[str] = []

    def set_link(
        *,
        value: str,
        conf: str,
        why: str,
        link_evidence: list[str],
        link_method: str = "deterministic",
    ) -> None:
        nonlocal link_type, confidence, method, reason, evidence
        link_type = value
        confidence = conf
        method = link_method
        reason = why
        evidence = link_evidence

    if _primary_target_matches(source, primary_target_source_id=primary_target_source_id):
        set_link(
            value="is_target",
            conf="high",
            why="Source marked/resolved as primary analysis target.",
            link_evidence=[
                f"source_record_id={source_record_id}",
                f"target_source_record_id={primary_target_source_id or source_record_id}",
            ],
        )
    elif _contains(searchable_text, r"\bcorrigendum\b") and target_linked:
        set_link(
            value="corrects",
            conf="high",
            why="Corrigendum references target citation/title family.",
            link_evidence=[f"title={tokens['title']}", f"target_citation={target_citation or ''}"],
        )
    elif _contains(searchable_text, r"\bamending\b|\bamendment\b") and target_linked:
        set_link(
            value="amends",
            conf="high",
            why="Amending/amendment marker references target citation/title family.",
            link_evidence=[f"title={tokens['title']}", f"target_citation={target_citation or ''}"],
        )
    elif _contains(searchable_text, r"\bimplementing regulation\b") and target_linked:
        set_link(
            value="implements",
            conf="high",
            why="Implementing regulation references target citation/title family.",
            link_evidence=[f"title={tokens['title']}", f"target_citation={target_citation or ''}"],
        )
    elif _contains(searchable_text, r"\bdelegated regulation\b") and target_linked:
        set_link(
            value="supplements",
            conf="high",
            why="Delegated regulation references target citation/title family.",
            link_evidence=[f"title={tokens['title']}", f"target_citation={target_citation or ''}"],
        )
    elif _contains(searchable_text, r"\bexplanatory memorandum\b|\bexplanatory note") and target_linked:
        set_link(
            value="explains",
            conf="high",
            why="Explanatory material references the target.",
            link_evidence=[f"title={tokens['title']}", f"target_title={primary_target_title or ''}"],
        )
    elif _contains(searchable_text, r"\bguidance\b"):
        set_link(
            value="explains" if target_linked else "contextual",
            conf="medium",
            why="Guidance source linked by target references when present.",
            link_evidence=[
                f"title={tokens['title']}",
                f"target_reference_match={target_linked}",
            ],
        )
    elif _contains(searchable_text, r"\bmodel certificate\b|\bhealth certificate\b|\bcertificate\b"):
        citation_family = _citation_family(tokens["citation"])
        target_family = _citation_family(primary_target_citation)
        family_match = bool(citation_family and target_family and citation_family == target_family)
        if target_linked or family_match:
            set_link(
                value="implements",
                conf="medium" if family_match and not target_linked else "high",
                why="Certificate model connected to target citation family.",
                link_evidence=[
                    f"title={tokens['title']}",
                    f"citation_family={citation_family}",
                    f"target_family={target_family}",
                ],
            )
        else:
            set_link(
                value="contextual",
                conf="low",
                why="Certificate material present without strong target linkage.",
                link_evidence=[f"title={tokens['title']}"],
            )
    elif _contains(searchable_text, r"\bannex\b"):
        parent_source_id = _to_text(metadata.get("parent_source_record_id"))
        if parent_source_id and primary_target_source_id and parent_source_id == primary_target_source_id:
            set_link(
                value="contains_annex_to",
                conf="high",
                why="Annex explicitly attached to target source via metadata parent link.",
                link_evidence=[
                    f"parent_source_record_id={parent_source_id}",
                    f"target_source_record_id={primary_target_source_id}",
                ],
            )
        elif target_linked:
            set_link(
                value="contains_annex_to",
                conf="medium",
                why="Annex references target citation/title.",
                link_evidence=[f"title={tokens['title']}", f"target_citation={target_citation or ''}"],
            )
        else:
            set_link(
                value="contextual",
                conf="medium",
                why="Annex source without clear target linkage.",
                link_evidence=[f"title={tokens['title']}"],
            )
    elif target_linked:
        set_link(
            value="references",
            conf="medium",
            why="Source references target citation/title but no stronger semantic link was found.",
            link_evidence=[f"title={tokens['title']}", f"target_citation={target_citation or ''}"],
        )
    else:
        set_link(
            value="contextual",
            conf="low",
            why="Source treated as contextual because no target linkage signals matched.",
            link_evidence=[f"title={tokens['title']}"],
        )

    if link_type not in TARGET_LINK_TYPES:
        link_type = "unknown"

    return SourceTargetLink(
        id=f"target-link-{source_record_id}",
        source_record_id=source_record_id,
        target_source_record_id=target_source_record_id if link_type != "is_target" else source_record_id,
        target_citation=target_citation,
        target_instrument_id=target_instrument_id,
        link_type=link_type,
        confidence=confidence,
        method=method,
        reason=reason,
        evidence=evidence,
        signals={
            "target_reference_match": target_linked,
            "primary_target_source_id": primary_target_source_id,
            "primary_target_citation": primary_target_citation,
            "primary_target_title": primary_target_title,
            "authority": tokens["authority"],
            "kind": tokens["kind"],
            "source_url": tokens["url"],
        },
    )


def classify_source_categorisation(
    *,
    source: Any,
    primary_target_citation: str | None = None,
    target_link: SourceTargetLink | None = None,
) -> SourceCategorisationRationale:
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    tokens = _tokens_from_source(source)
    searchable_text = tokens["searchable_text_lower"]
    source_record_id = str(source.id)
    source_role = "unknown"
    relationship = LINK_TO_RELATIONSHIP.get(
        target_link.link_type if target_link else "unknown", "unknown"
    )
    confidence = "low"
    method = "fallback"
    reason = "No deterministic categorisation rule matched."
    evidence: list[str] = []
    target_linked = _target_linked(source, primary_target_citation=primary_target_citation)

    def set_result(
        *,
        role: str,
        rel: str,
        conf: str,
        why: str,
        signals: list[str],
        resolved_method: str = "deterministic",
    ) -> None:
        nonlocal source_role, relationship, confidence, reason, evidence, method
        source_role = role
        relationship = rel
        confidence = conf
        reason = why
        method = resolved_method
        evidence = signals

    is_case_file = _contains(tokens["authority"], r"\bcase_file\b") or _contains(
        _to_text(metadata.get("adapter") or ""), r"CaseFileAuthorityAdapter"
    )
    if is_case_file:
        set_result(
            role="case_file",
            rel="analysis_target",
            conf="high",
            why="Case-file authority source treated as direct analysis input.",
            signals=[
                f"authority={tokens['authority'] or 'case_file'}",
                f"source_record_id={source_record_id}",
            ],
        )
    elif _contains(searchable_text, r"\bcorrigendum\b"):
        set_result(
            role="corrigendum",
            rel="modifies_target",
            conf="high",
            why="Corrigendum indicator implies corrective modification of target text.",
            signals=[f"title={tokens['title']}", f"citation={tokens['citation']}"],
        )
    elif _contains(searchable_text, r"\bamending\b|\bamendment\b"):
        set_result(
            role="amendment",
            rel="modifies_target",
            conf="high",
            why="Amending/amendment marker found in source descriptors.",
            signals=[f"title={tokens['title']}", f"kind={tokens['kind']}"],
        )
    elif _contains(searchable_text, r"\bdelegated regulation\b"):
        set_result(
            role="delegated_act",
            rel="implements_target" if target_linked else "contextual_source",
            conf="high" if target_linked else "medium",
            why="Delegated regulation marker found in source descriptors.",
            signals=[f"title={tokens['title']}", f"target_linked={target_linked}"],
        )
    elif _contains(searchable_text, r"\bimplementing regulation\b"):
        set_result(
            role="implementing_act",
            rel="implements_target",
            conf="high",
            why="Implementing regulation marker found in source descriptors.",
            signals=[f"title={tokens['title']}", f"citation={tokens['citation']}"],
        )
    elif _contains(searchable_text, r"\bexplanatory memorandum\b|\bexplanatory note"):
        set_result(
            role="explanatory_material",
            rel="explains_target",
            conf="high",
            why="Explanatory material marker found in title or metadata.",
            signals=[f"title={tokens['title']}", f"long_title={_to_text(metadata.get('long_title'))}"],
        )
    elif _contains(searchable_text, r"\bguidance\b"):
        set_result(
            role="guidance",
            rel="explains_target" if target_linked else "contextual_source",
            conf="medium",
            why="Guidance marker found in source descriptors.",
            signals=[f"title={tokens['title']}", f"target_linked={target_linked}"],
        )
    elif _contains(searchable_text, r"\bmodel certificate\b|\bhealth certificate\b|\bcertificate\b"):
        set_result(
            role="certificate_model",
            rel="implements_target",
            conf="high",
            why="Certificate marker indicates operational model/certificate material.",
            signals=[f"title={tokens['title']}", f"kind={tokens['kind']}"],
        )
    elif _contains(searchable_text, r"\bannex\b"):
        set_result(
            role="annex",
            rel="evidences_target" if target_linked else "contextual_source",
            conf="medium",
            why="Annex marker found; treated as contextual unless clearly target-linked.",
            signals=[f"title={tokens['title']}", f"target_linked={target_linked}"],
        )
    elif (
        (
            "legislation.gov.uk" in tokens["url"].lower()
            or "eur-lex.europa.eu" in tokens["url"].lower()
            or _contains(tokens["authority"], r"legislation_gov_uk|eur-lex|eurlex")
        )
        and target_linked
        and _contains(searchable_text, r"\b(regulation|act)\b")
    ):
        set_result(
            role="base_act",
            rel="analysis_target",
            conf="high",
            why="Authoritative legislation source matches target citation and instrument type.",
            signals=[
                f"source_url={tokens['url']}",
                f"citation={tokens['citation']}",
                f"primary_target_citation={primary_target_citation or ''}",
            ],
        )
    elif _contains(searchable_text, r"\b(regulation|act)\b") and target_linked:
        set_result(
            role="base_act",
            rel="analysis_target",
            conf="medium",
            why="Target-linked regulation/act source inferred as base act.",
            signals=[
                f"citation={tokens['citation']}",
                f"primary_target_citation={primary_target_citation or ''}",
            ],
        )

    if source_role not in SOURCE_ROLES:
        source_role = "unknown"
    if target_link:
        relationship = LINK_TO_RELATIONSHIP.get(target_link.link_type, "unknown")
    if relationship not in RELATIONSHIPS:
        relationship = "unknown"
    if target_link and target_link.confidence == "low" and confidence == "high":
        confidence = "medium"
    if target_link and target_link.method == "fallback" and method != "fallback":
        method = "deterministic"

    return SourceCategorisationRationale(
        source_record_id=source_record_id,
        source_target_link_id=target_link.id if target_link else None,
        source_role=source_role,
        relationship_to_analysis=relationship,
        confidence=confidence,
        method=method,
        reason=reason,
        evidence=evidence,
        signals={
            "target_linked": target_linked,
            "authority": tokens["authority"],
            "citation": tokens["citation"],
            "source_url": tokens["url"],
            "kind": tokens["kind"],
            "instrument_id": tokens["instrument_id"],
        },
    )
