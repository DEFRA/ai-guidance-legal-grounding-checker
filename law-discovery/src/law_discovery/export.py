from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from law_discovery.models import (
    CandidateSource,
    SourceBundle,
    SourceRegister,
    SourceRelationship,
    load_source_register,
    save_source_register,
)


def export_register_json(register: SourceRegister, *, indent: int = 2) -> str:
    return register.model_dump_json(indent=indent)


def write_register(register: SourceRegister, path: Path) -> None:
    save_source_register(register, path)


def load_register(path: Path) -> SourceRegister:
    return load_source_register(path)


def _format_created_at(created_at: datetime) -> str:
    return created_at.isoformat().replace("+00:00", "Z")


def _export_source(source: CandidateSource) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "title": source.title,
        "citation": source.citation,
        "source_type": source.source_type,
        "canonical_uri": source.canonical_uri,
        "source_system": source.source_system,
        "relationship_to_category": source.relationship_to_category,
        "confidence": source.confidence,
        "ada_review_status": "accepted",
        "evidence": [snippet.model_dump() for snippet in source.evidence],
    }


def export_selected_sources_for_judit(register: SourceRegister) -> dict[str, Any]:
    """Export accepted register sources as a plain JSON handoff contract for Law Proposition Extractor."""
    return {
        "export_type": "ada_selected_sources_for_judit",
        "export_version": "0.1",
        "category_id": register.category_id,
        "created_at": _format_created_at(register.created_at),
        "sources": [_export_source(source) for source in register.accepted_sources],
    }


def save_selected_sources_for_judit(register: SourceRegister, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = export_selected_sources_for_judit(register)
    path.write_text(f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n", encoding="utf-8")
    from law_discovery.run_model_md import persist_model_md_for_source_register

    persist_model_md_for_source_register(
        register,
        path,
        run_kind="law-proposition-extractor-selected-sources",
    )


def export_judit_handoff_json(register: SourceRegister, *, indent: int = 2) -> str:
    return json.dumps(export_selected_sources_for_judit(register), indent=indent)


def write_judit_handoff(register: SourceRegister, path: Path) -> None:
    save_selected_sources_for_judit(register, path)


def _export_bundle_source(source: CandidateSource) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "title": source.title,
        "citation": source.citation,
        "source_type": source.source_type,
        "canonical_uri": source.canonical_uri,
        "source_system": source.source_system,
        "confidence": source.confidence,
        "review_status": source.review_status,
        "evidence": [snippet.model_dump() for snippet in source.evidence],
    }


def _export_relationship(relationship: SourceRelationship) -> dict[str, Any]:
    return {
        "relationship_id": relationship.relationship_id,
        "from_source_id": relationship.from_source_id,
        "to_source_id": relationship.to_source_id,
        "relationship_type": relationship.relationship_type,
        "confidence": relationship.confidence,
        "basis": relationship.basis,
        "evidence": [snippet.model_dump() for snippet in relationship.evidence],
        "review_status": relationship.review_status,
        "notes": relationship.notes,
    }


def export_source_bundle_for_judit(bundle: SourceBundle) -> dict[str, Any]:
    """Export a source bundle as a richer Law Proposition Extractor handoff contract (no legal effect resolved)."""
    return {
        "export_type": "ada_source_bundle_for_judit",
        "export_version": "0.1",
        "category_id": bundle.category_id,
        "created_at": _format_created_at(bundle.created_at),
        "source_bundles": [
            {
                "bundle_id": bundle.bundle_id,
                "principal_sources": [
                    _export_bundle_source(source) for source in bundle.principal_sources
                ],
                "amending_sources": [
                    _export_bundle_source(source) for source in bundle.amending_sources
                ],
                "commencement_sources": [
                    _export_bundle_source(source) for source in bundle.commencement_sources
                ],
                "correction_sources": [
                    _export_bundle_source(source) for source in bundle.correction_sources
                ],
                "revocation_sources": [
                    _export_bundle_source(source) for source in bundle.revocation_sources
                ],
                "interpretive_sources": [
                    _export_bundle_source(source) for source in bundle.interpretive_sources
                ],
                "guidance_sources": [
                    _export_bundle_source(source) for source in bundle.guidance_sources
                ],
                "form_sources": [
                    _export_bundle_source(source) for source in bundle.form_sources
                ],
                "contextual_sources": [
                    _export_bundle_source(source) for source in bundle.contextual_sources
                ],
                "relationships": [
                    _export_relationship(relationship) for relationship in bundle.relationships
                ],
            }
        ],
    }


def save_source_bundle_for_judit(bundle: SourceBundle, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = export_source_bundle_for_judit(bundle)
    path.write_text(f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n", encoding="utf-8")
    from law_discovery.run_model_md import persist_model_md_for_source_bundle

    persist_model_md_for_source_bundle(
        bundle,
        path,
        run_kind="law-proposition-extractor-source-bundle-export",
    )
