from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import streamlit as st

from law_discovery.export import export_register_json, export_selected_sources_for_judit
from law_discovery.models import (
    CandidateSource,
    CandidateTriageMetadata,
    Confidence,
    DiscoveryRun,
    RecommendedAction,
    RelatedSourceExpansionRun,
    RelatedSourceRelationshipType,
    ReviewPriority,
    ReviewStatus,
    SourceBundle,
    SourceRelationship,
    load_discovery_run,
    load_related_source_expansion_run,
    load_source_bundle,
)
from law_discovery.triage_helpers import (
    AI_TRIAGE_MARKER,
    count_by_recommended_action,
    count_by_review_priority,
    discovery_run_has_ai_triage,
    has_ai_triage_notes,
)
from law_discovery.viewer_helpers import (
    build_source_register_from_reviews,
    count_by_confidence,
    count_by_review_status,
    effective_review_status,
    filter_candidates,
)

SESSION_REVIEWS_KEY = "reviews"
SESSION_RUN_PATH_KEY = "discovery_run_path"
SESSION_RELATIONSHIP_REVIEWS_KEY = "relationship_reviews"


def _detect_viewer_payload(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "seed_sources" in payload and "relationships" in payload:
        return "related_expansion"
    if isinstance(payload, dict) and "bundle_id" in payload and "principal_sources" in payload:
        return "source_bundle"
    return "discovery_run"


def resolve_discovery_run_path() -> Path | None:
    args = sys.argv[1:]
    for arg in reversed(args):
        if arg.startswith("-"):
            continue
        path = Path(arg)
        if path.suffix == ".json" and path.exists():
            return path.resolve()
    return None


def _init_session_state(run: DiscoveryRun, run_path: Path) -> None:
    if st.session_state.get(SESSION_RUN_PATH_KEY) != str(run_path):
        st.session_state[SESSION_RUN_PATH_KEY] = str(run_path)
        st.session_state[SESSION_REVIEWS_KEY] = {
            candidate.source_id: candidate.review_status
            for candidate in run.candidate_sources
        }


def _reviews() -> dict[str, ReviewStatus]:
    return st.session_state.setdefault(SESSION_REVIEWS_KEY, {})


def _set_review(source_id: str, status: ReviewStatus) -> None:
    reviews = _reviews()
    reviews[source_id] = status
    st.session_state[SESSION_REVIEWS_KEY] = reviews


def _bulk_set_review(candidates: list[CandidateSource], status: ReviewStatus) -> None:
    reviews = _reviews()
    for candidate in candidates:
        reviews[candidate.source_id] = status
    st.session_state[SESSION_REVIEWS_KEY] = reviews


def _render_structured_triage(triage: CandidateTriageMetadata) -> None:
    st.write(
        f"**Relevance:** {triage.relevance} · **Review priority:** {triage.review_priority} · "
        f"**Recommended action:** {triage.recommended_action} · "
        f"**Relevance confidence:** {triage.confidence_after_ai}"
    )
    st.markdown(f"**Rationale:** {triage.rationale}")
    if triage.supporting_signals:
        st.write("**Supporting signals:**")
        for signal in triage.supporting_signals:
            st.markdown(f"- {signal}")
    if triage.false_positive_risks:
        st.write("**False positive risks:**")
        for risk in triage.false_positive_risks:
            st.markdown(f"- {risk}")
    if triage.evidence_limitations:
        st.write("**Evidence limitations:**")
        for limitation in triage.evidence_limitations:
            st.markdown(f"- {limitation}")


def _render_candidate_card(candidate: CandidateSource, reviews: dict[str, ReviewStatus]) -> None:
    status = effective_review_status(candidate, reviews)
    with st.container(border=True):
        st.subheader(candidate.title)
        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.caption(f"**Citation:** {candidate.citation or '—'}")
            st.write(
                f"**Type:** {candidate.source_type} · **System:** {candidate.source_system} · "
                f"**Confidence:** {candidate.confidence} · **Relationship:** "
                f"{candidate.relationship_to_category}"
            )
            if candidate.ai_triage is not None:
                st.write(
                    f"**AI triage:** {candidate.ai_triage.review_priority} · "
                    f"{candidate.ai_triage.recommended_action} · "
                    f"relevance confidence {candidate.ai_triage.confidence_after_ai}"
                )
            st.write(f"**Review status:** {status}")
            if candidate.canonical_uri:
                st.markdown(f"[{candidate.canonical_uri}]({candidate.canonical_uri})")
            else:
                st.caption("No canonical URI")
            if candidate.matched_terms:
                st.write("**Matched terms:**", ", ".join(candidate.matched_terms))
            if candidate.evidence:
                with st.expander("Evidence snippets"):
                    for snippet in candidate.evidence:
                        st.markdown(f"- **{snippet.evidence_type}:** {snippet.text}")
                        if snippet.uri:
                            st.caption(snippet.uri)
            if candidate.ai_triage is not None:
                with st.expander("AI triage assessment", expanded=True):
                    _render_structured_triage(candidate.ai_triage)
            elif candidate.notes and has_ai_triage_notes(candidate):
                prefix, _, triage_body = candidate.notes.partition(AI_TRIAGE_MARKER)
                with st.expander("AI triage assessment", expanded=True):
                    st.markdown(f"**{AI_TRIAGE_MARKER}** {triage_body.strip()}")
                if prefix.strip():
                    st.caption("Other notes")
                    st.info(prefix.strip())
            elif candidate.notes:
                st.info(candidate.notes)

        with cols[1]:
            if st.button("Accept", key=f"accept-{candidate.source_id}"):
                _set_review(candidate.source_id, "accepted")
                st.rerun()
            if st.button("Park", key=f"park-{candidate.source_id}"):
                _set_review(candidate.source_id, "parked")
                st.rerun()
        with cols[2]:
            if st.button("Reject", key=f"reject-{candidate.source_id}"):
                _set_review(candidate.source_id, "rejected")
                st.rerun()
            if st.button("Needs research", key=f"research-{candidate.source_id}"):
                _set_review(candidate.source_id, "needs_more_research")
                st.rerun()


def _title_by_id(sources: list[CandidateSource]) -> dict[str, str]:
    return {source.source_id: source.title for source in sources}


def _render_related_expansion_viewer(run: RelatedSourceExpansionRun, run_path: Path) -> None:
    st.title("Law Discovery Related Source Expansion")
    st.caption(
        f"**category_id:** `{run.category_id}` · **run_id:** `{run.run_id}` · "
        f"**seed sources:** {len(run.seed_sources)} · "
        f"**related sources:** {len(run.related_sources)} · "
        f"**relationships:** {len(run.relationships)}"
    )

    titles = _title_by_id([*run.seed_sources, *run.related_sources])

    with st.expander(f"Seed sources ({len(run.seed_sources)})", expanded=False):
        for source in run.seed_sources:
            st.markdown(f"- **{source.title}** (`{source.source_id}`)")

    with st.expander(f"Related sources ({len(run.related_sources)})", expanded=False):
        for source in run.related_sources:
            st.markdown(f"- **{source.title}** (`{source.source_id}`)")

    relationship_types: list[RelatedSourceRelationshipType] = sorted(
        {relationship.relationship_type for relationship in run.relationships}
    )
    confidence_options: list[Confidence] = sorted(
        {relationship.confidence for relationship in run.relationships}
    )
    review_options: list[ReviewStatus] = [
        "unreviewed",
        "accepted",
        "parked",
        "rejected",
        "needs_more_research",
    ]

    with st.sidebar:
        st.header("Relationship filters")
        type_filter = st.multiselect(
            "Relationship type",
            relationship_types,
            default=relationship_types,
        )
        confidence_filter = st.multiselect(
            "Confidence",
            confidence_options,
            default=confidence_options,
        )
        review_filter = st.multiselect(
            "Review status",
            review_options,
            default=review_options,
        )

    relationship_reviews = st.session_state.setdefault(SESSION_RELATIONSHIP_REVIEWS_KEY, {})
    visible_relationships = [
        relationship
        for relationship in run.relationships
        if relationship.relationship_type in type_filter
        and relationship.confidence in confidence_filter
        and relationship_reviews.get(
            relationship.relationship_id, relationship.review_status
        )
        in review_filter
    ]

    st.subheader(f"Relationships ({len(visible_relationships)} visible)")
    for relationship in visible_relationships:
        status = relationship_reviews.get(
            relationship.relationship_id, relationship.review_status
        )
        from_title = titles.get(relationship.from_source_id, relationship.from_source_id)
        to_title = titles.get(relationship.to_source_id, relationship.to_source_id)
        with st.container(border=True):
            st.markdown(
                f"**{relationship.relationship_type}** · confidence: {relationship.confidence} · "
                f"review: {status}"
            )
            st.write(f"**From:** {from_title}")
            st.write(f"**To:** {to_title}")
            if relationship.basis:
                st.caption(f"Basis: {', '.join(relationship.basis)}")
            if relationship.notes:
                st.info(relationship.notes)
            cols = st.columns(4)
            if cols[0].button("Accept", key=f"rel-accept-{relationship.relationship_id}"):
                relationship_reviews[relationship.relationship_id] = "accepted"
                st.session_state[SESSION_RELATIONSHIP_REVIEWS_KEY] = relationship_reviews
                st.rerun()
            if cols[1].button("Park", key=f"rel-park-{relationship.relationship_id}"):
                relationship_reviews[relationship.relationship_id] = "parked"
                st.session_state[SESSION_RELATIONSHIP_REVIEWS_KEY] = relationship_reviews
                st.rerun()
            if cols[2].button("Reject", key=f"rel-reject-{relationship.relationship_id}"):
                relationship_reviews[relationship.relationship_id] = "rejected"
                st.session_state[SESSION_RELATIONSHIP_REVIEWS_KEY] = relationship_reviews
                st.rerun()
            if cols[3].button("Research", key=f"rel-research-{relationship.relationship_id}"):
                relationship_reviews[relationship.relationship_id] = "needs_more_research"
                st.session_state[SESSION_RELATIONSHIP_REVIEWS_KEY] = relationship_reviews
                st.rerun()

    updated_relationships: list[SourceRelationship] = []
    for relationship in run.relationships:
        status = relationship_reviews.get(relationship.relationship_id)
        if status is None:
            updated_relationships.append(relationship)
        else:
            updated_relationships.append(
                relationship.model_copy(update={"review_status": status})
            )
    updated_run = run.model_copy(update={"relationships": updated_relationships})
    st.download_button(
        "Download related-sources-run.json",
        data=updated_run.model_dump_json(indent=2),
        file_name=run_path.name,
        mime="application/json",
    )


def _render_source_bundle_viewer(bundle: SourceBundle) -> None:
    st.title("Law Discovery Source Bundle")
    st.caption(
        f"**category_id:** `{bundle.category_id}` · **bundle_id:** `{bundle.bundle_id}` · "
        f"**relationships:** {len(bundle.relationships)}"
    )

    buckets = [
        ("Principal", bundle.principal_sources),
        ("Amending", bundle.amending_sources),
        ("Commencement", bundle.commencement_sources),
        ("Correction", bundle.correction_sources),
        ("Revocation", bundle.revocation_sources),
        ("Interpretive", bundle.interpretive_sources),
        ("Guidance", bundle.guidance_sources),
        ("Form", bundle.form_sources),
        ("Contextual", bundle.contextual_sources),
        ("Rejected", bundle.rejected_sources),
    ]
    for label, sources in buckets:
        with st.expander(f"{label} ({len(sources)})", expanded=label == "Principal"):
            for source in sources:
                st.markdown(f"- **{source.title}** (`{source.source_id}`)")

    if bundle.relationships:
        st.subheader("Relationships")
        titles = _title_by_id(
            [
                *bundle.principal_sources,
                *bundle.amending_sources,
                *bundle.commencement_sources,
                *bundle.correction_sources,
                *bundle.revocation_sources,
                *bundle.interpretive_sources,
                *bundle.guidance_sources,
                *bundle.form_sources,
                *bundle.contextual_sources,
                *bundle.rejected_sources,
            ]
        )
        rows = [
            {
                "type": relationship.relationship_type,
                "from": titles.get(relationship.from_source_id, relationship.from_source_id),
                "to": titles.get(relationship.to_source_id, relationship.to_source_id),
                "confidence": relationship.confidence,
                "review": relationship.review_status,
            }
            for relationship in bundle.relationships
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def run_viewer() -> None:
    st.set_page_config(page_title="Law Discovery Source Review", layout="wide")

    run_path = resolve_discovery_run_path()
    if run_path is None:
        st.title("Law Discovery Source Review")
        st.error(
            "No JSON file provided. Run:\n\n"
            "`uv run law-discovery-viewer runs/animal_by_products/discovery-run.json`\n\n"
            "Also supports related-sources-run.json and source-bundle.json."
        )
        return

    payload_kind = _detect_viewer_payload(run_path)
    if payload_kind == "related_expansion":
        _render_related_expansion_viewer(
            load_related_source_expansion_run(run_path),
            run_path,
        )
        return
    if payload_kind == "source_bundle":
        _render_source_bundle_viewer(load_source_bundle(run_path))
        return

    run = load_discovery_run(run_path)
    _init_session_state(run, run_path)
    reviews = _reviews()

    st.title("Law Discovery Source Review")
    st.header(run.category.label)
    st.caption(
        f"**category_id:** `{run.category.category_id}` · "
        f"**run_id:** `{run.run_id}` · "
        f"**created_at:** {run.created_at.isoformat()} · "
        f"**queries:** {len(run.query_plan)} · "
        f"**candidates:** {len(run.candidate_sources)}"
    )

    if run.metadata.get("ai_triage_failed") is True:
        st.error(
            "AI triage failed; all AI triage values are fallback/uncertain.",
            icon="⚠️",
        )
    elif run.metadata.get("ai_triage_partial") is True:
        st.warning("AI triage partially failed.", icon="⚠️")

    has_ai_triage = discovery_run_has_ai_triage(run.candidate_sources)
    confidence_counts = count_by_confidence(run.candidate_sources)
    review_counts = count_by_review_status(run.candidate_sources, reviews)

    if has_ai_triage:
        priority_counts = count_by_review_priority(run.candidate_sources)
        metric_cols = st.columns(6)
        metric_cols[0].metric("Candidates", len(run.candidate_sources))
        metric_cols[1].metric("Likely accept", priority_counts["likely_accept"])
        metric_cols[2].metric("Needs review", priority_counts["needs_human_review"])
        metric_cols[3].metric("Park contextual", priority_counts["park_contextual"])
        metric_cols[4].metric("Likely reject", priority_counts["likely_reject"])
        metric_cols[5].metric("Warnings", len(run.warnings))
        action_counts = count_by_recommended_action(run.candidate_sources)
        st.caption(
            f"Accept action: {action_counts['accept_candidate']} · "
            f"Park: {action_counts['park']} · Reject action: "
            f"{action_counts['reject_candidate']} · Needs research: "
            f"{action_counts['needs_more_research']} · "
            f"Confidence (post-AI): high={confidence_counts['high']} "
            f"medium={confidence_counts['medium']} low={confidence_counts['low']}"
        )
    else:
        metric_cols = st.columns(6)
        metric_cols[0].metric("Candidates", len(run.candidate_sources))
        metric_cols[1].metric("High confidence", confidence_counts["high"])
        metric_cols[2].metric("Medium", confidence_counts["medium"])
        metric_cols[3].metric("Low", confidence_counts["low"])
        metric_cols[4].metric("Accepted", review_counts["accepted"])
        metric_cols[5].metric("Warnings", len(run.warnings))
        st.caption(
            f"Unreviewed: {review_counts['unreviewed']} · Parked: {review_counts['parked']} · "
            f"Rejected: {review_counts['rejected']} · Needs research: "
            f"{review_counts['needs_more_research']} · Unknown confidence: "
            f"{confidence_counts['unknown']}"
        )

    if run.warnings:
        with st.expander(f"Warnings ({len(run.warnings)})"):
            for warning in run.warnings:
                st.warning(warning)

    with st.sidebar:
        st.header("Filters")
        text_query = st.text_input("Search title / URI")
        matched_terms_query = st.text_input("Matched terms contain")
        confidence_options: list[Confidence] = sorted({c.confidence for c in run.candidate_sources})
        source_type_options = sorted({c.source_type for c in run.candidate_sources})
        relationship_options = sorted({c.relationship_to_category for c in run.candidate_sources})
        review_options: list[ReviewStatus] = [
            "unreviewed",
            "accepted",
            "parked",
            "rejected",
            "needs_more_research",
        ]

        confidence_filter = cast(
            list[Confidence],
            st.multiselect("Confidence", confidence_options, default=confidence_options),
        )
        source_type_filter = st.multiselect(
            "Source type", source_type_options, default=source_type_options
        )
        relationship_filter = st.multiselect(
            "Relationship to category",
            relationship_options,
            default=relationship_options,
        )
        review_filter = st.multiselect("Review status", review_options, default=review_options)
        hide_low = st.checkbox("Hide low confidence")
        hide_revoked = st.checkbox("Hide revoked-looking titles")
        hide_noise = st.checkbox("Hide obvious local/private/traffic acts")
        only_abp = st.checkbox("Only ABP-related titles")
        ai_triage_filter = st.selectbox(
            "AI triage",
            ["All", "AI triaged", "Not triaged"],
            index=0,
        )
        ai_priority_filter = st.selectbox(
            "AI review priority",
            [
                "All",
                "likely_accept",
                "needs_human_review",
                "park_contextual",
                "likely_reject",
            ],
            index=0,
        )
        ai_action_filter = st.selectbox(
            "AI recommended action",
            [
                "All",
                "accept_candidate",
                "park",
                "reject_candidate",
                "needs_more_research",
            ],
            index=0,
        )
        ai_likely_accept = st.checkbox("AI likely accept (legacy)")
        ai_likely_reject = st.checkbox("AI likely reject (legacy)")

        only_ai_triaged: bool | None = None
        if ai_triage_filter == "AI triaged":
            only_ai_triaged = True
        elif ai_triage_filter == "Not triaged":
            only_ai_triaged = False

        ai_review_priority: ReviewPriority | None = (
            None if ai_priority_filter == "All" else cast(ReviewPriority, ai_priority_filter)
        )
        ai_recommended_action: RecommendedAction | None = (
            None if ai_action_filter == "All" else cast(RecommendedAction, ai_action_filter)
        )

        def _filter_kwargs() -> dict[str, Any]:
            return {
                "text_query": text_query,
                "confidence": confidence_filter,
                "source_types": source_type_filter,
                "relationships": relationship_filter,
                "review_statuses": review_filter,
                "matched_terms_query": matched_terms_query,
                "hide_low_confidence": hide_low,
                "hide_revoked_looking": hide_revoked,
                "hide_obvious_noise": hide_noise,
                "only_abp_titles": only_abp,
                "only_ai_triaged": only_ai_triaged,
                "ai_likely_accept": ai_likely_accept,
                "ai_likely_reject": ai_likely_reject,
                "ai_review_priority": ai_review_priority,
                "ai_recommended_action": ai_recommended_action,
            }

        def _visible() -> list[CandidateSource]:
            return filter_candidates(run.candidate_sources, reviews, **_filter_kwargs())

        st.divider()
        st.header("Bulk actions (visible)")
        if st.button("Accept all visible high-confidence"):
            visible = _visible()
            high_visible = [c for c in visible if c.confidence == "high"]
            _bulk_set_review(high_visible, "accepted")
            st.rerun()
        if st.button("Park all visible"):
            _bulk_set_review(_visible(), "parked")
            st.rerun()
        if st.button("Reject all visible low-confidence"):
            low_visible = [c for c in _visible() if c.confidence == "low"]
            _bulk_set_review(low_visible, "rejected")
            st.rerun()
        if st.button("Reset visible to unreviewed"):
            _bulk_set_review(_visible(), "unreviewed")
            st.rerun()

    visible_candidates = filter_candidates(
        run.candidate_sources,
        reviews,
        text_query=text_query,
        confidence=confidence_filter,
        source_types=source_type_filter,
        relationships=relationship_filter,
        review_statuses=review_filter,
        matched_terms_query=matched_terms_query,
        hide_low_confidence=hide_low,
        hide_revoked_looking=hide_revoked,
        hide_obvious_noise=hide_noise,
        only_abp_titles=only_abp,
        only_ai_triaged=only_ai_triaged,
        ai_likely_accept=ai_likely_accept,
        ai_likely_reject=ai_likely_reject,
        ai_review_priority=ai_review_priority,
        ai_recommended_action=ai_recommended_action,
    )

    register = build_source_register_from_reviews(run, reviews)
    st.divider()
    export_cols = st.columns(2)
    with export_cols[0]:
        st.download_button(
            "Download source-register.json",
            data=export_register_json(register),
            file_name="source-register.json",
            mime="application/json",
        )
    with export_cols[1]:
        judit_payload = json.dumps(
            export_selected_sources_for_judit(register),
            indent=2,
            ensure_ascii=False,
        )
        st.download_button(
            "Download selected-sources-for-law-proposition-extractor.json",
            data=judit_payload,
            file_name="selected-sources-for-law-proposition-extractor.json",
            mime="application/json",
        )

    st.subheader(f"Candidates ({len(visible_candidates)} visible)")
    for candidate in visible_candidates:
        _render_candidate_card(candidate, reviews)


def cli_main() -> None:
    viewer_path = Path(__file__).resolve()
    extra_args = sys.argv[1:]
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(viewer_path),
        "--server.headless",
        "true",
        "--",
        *extra_args,
    ]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    run_viewer()
