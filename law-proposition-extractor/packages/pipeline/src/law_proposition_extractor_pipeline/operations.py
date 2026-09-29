import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import unified_diff
from pathlib import Path
from typing import Any

from . import proposition_explorer_grouping as peg
from .effective_views import resolve_effective_artifact_view
from .pipeline_run_jobs import RunJobStore


class OperationsError(ValueError):
    """Raised when operational artifacts cannot be resolved."""


@dataclass(frozen=True)
class RunIndexEntry:
    run_id: str
    run_dir: Path
    manifest: dict[str, Any]
    run_payload: dict[str, Any]


class OperationalStore:
    def __init__(
        self,
        export_dir: str | Path = "dist/static-report",
        source_registry_path: str | Path | None = None,
    ) -> None:
        self.export_dir = Path(export_dir)
        self.source_registry_path = Path(source_registry_path) if source_registry_path else None

    def list_runs(self) -> list[dict[str, Any]]:
        entries = sorted(
            self._run_index(),
            key=lambda item: (
                str(item.run_payload.get("created_at", "")),
                item.run_id,
            ),
            reverse=True,
        )
        return [
            {
                "run_id": item.run_id,
                "workflow_mode": item.manifest.get("workflow_mode"),
                "proposition_count": item.manifest.get("proposition_count"),
                "divergence_assessment_count": item.manifest.get("divergence_assessment_count"),
                "artifact_count": item.manifest.get("artifact_count"),
                "stage_trace_count": item.manifest.get("stage_trace_count"),
                "created_at": item.run_payload.get("created_at"),
                "run_dir": str(item.run_dir.relative_to(self.export_dir)),
            }
            for item in entries
        ]

    def inspect_run(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        trace_manifest = self._read_json_file(entry.run_dir / "trace-manifest.json", default={})
        return {
            "run": entry.run_payload,
            "manifest": entry.manifest,
            "trace_manifest": trace_manifest,
        }

    def list_run_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return RunJobStore(self.export_dir).list_jobs(limit=limit)

    def get_run_job(self, *, job_id: str) -> dict[str, Any]:
        job = RunJobStore(self.export_dir).read_job(job_id)
        if not job:
            raise OperationsError(f"Run job not found: {job_id}")
        return job

    def list_run_job_events(self, *, job_id: str) -> dict[str, Any]:
        self.get_run_job(job_id=job_id)
        events = RunJobStore(self.export_dir).read_events(job_id)
        return {"job_id": job_id, "events": events}

    def equine_corpus_coverage(self) -> dict[str, Any]:
        """Load equine corpus coverage files from the export root (if present)."""
        src_path = self.export_dir / "equine_source_coverage.json"
        prop_path = self.export_dir / "equine_proposition_coverage.json"
        if not src_path.is_file() or not prop_path.is_file():
            raise OperationsError(
                "Equine corpus coverage artifacts not found (expected equine_source_coverage.json "
                "and equine_proposition_coverage.json beside runs/)."
            )
        try:
            source_cov = json.loads(src_path.read_text(encoding="utf-8"))
            proposition_cov = json.loads(prop_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise OperationsError(f"Failed to read corpus coverage JSON: {exc}") from exc
        if not isinstance(source_cov, dict) or not isinstance(proposition_cov, dict):
            raise OperationsError("Corpus coverage files must contain JSON objects.")
        readiness_payload: dict[str, Any] | None = None
        readiness_path = self.export_dir / "equine_corpus_readiness.json"
        if readiness_path.is_file():
            try:
                raw_r = json.loads(readiness_path.read_text(encoding="utf-8"))
                if isinstance(raw_r, dict):
                    readiness_payload = raw_r
            except (OSError, json.JSONDecodeError):
                readiness_payload = None
        out: dict[str, Any] = {
            "export_dir": str(self.export_dir),
            "source_coverage": source_cov,
            "proposition_coverage": proposition_cov,
        }
        if readiness_payload:
            out["corpus_readiness"] = readiness_payload
            su = readiness_payload.get("source_universe")
            if isinstance(su, dict):
                out["source_universe"] = su
        return out

    def list_stage_traces(self, run_id: str | None = None, *, compact: bool = True) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        trace_manifest = self._read_json_file(entry.run_dir / "trace-manifest.json", default={})
        stages_raw = trace_manifest.get("stages", [])
        if not isinstance(stages_raw, list):
            stages_raw = []

        traces: list[dict[str, Any]] = []
        for stage in stages_raw:
            if not isinstance(stage, dict):
                continue
            storage_uri = stage.get("storage_uri")
            trace_payload = (
                self._read_by_storage_uri(str(storage_uri)) if isinstance(storage_uri, str) else {}
            )
            traces.append(
                {
                    "order": stage.get("order"),
                    "stage_name": stage.get("stage_name"),
                    "storage_uri": storage_uri,
                    "trace": trace_payload,
                }
            )

        extraction_inspection: dict[str, Any] | None = None
        try:
            from law_proposition_extractor_pipeline.extraction_llm_metrics import build_extraction_job_inspection
            from law_proposition_extractor_pipeline.linting import load_exported_bundle

            bundle = load_exported_bundle(self.export_dir)
            if str(bundle.get("run", {}).get("id") or "") == entry.run_id or not run_id:
                extraction_inspection = build_extraction_job_inspection(bundle)
        except (ValueError, OSError):
            extraction_inspection = None

        out: dict[str, Any] = {"run_id": entry.run_id, "trace_count": len(traces), "traces": traces}
        if extraction_inspection is not None:
            out["extraction_job_inspection"] = extraction_inspection
        elif (self.export_dir / "case.json").is_file() and not (entry.run_dir / "trace-manifest.json").is_file():
            out["hint"] = (
                "Export directory contains case.json only (run-bundle output). "
                "Re-run with `law-proposition-extractor-run-case export-run` (or `export-case` on a persisted run) to inspect extraction jobs."
            )
        if compact:
            from law_proposition_extractor_pipeline.extraction_llm_metrics import summarize_stage_traces_compact

            compact_out = summarize_stage_traces_compact(
                traces,
                extraction_job_inspection=extraction_inspection,
            )
            compact_out["run_id"] = entry.run_id
            return compact_out
        return out

    def list_review_decisions(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        decisions = self._artifact_list(entry=entry, artifact_type="review_decisions")
        return {"run_id": entry.run_id, "review_decisions": decisions}

    def list_pipeline_review_decisions(
        self,
        run_id: str | None = None,
        *,
        artifact_type: str | None = None,
        artifact_id: str | None = None,
        decision: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        rows = self._artifact_list(entry=entry, artifact_type="pipeline_review_decisions")
        if artifact_type:
            rows = [r for r in rows if str(r.get("artifact_type", "")) == artifact_type]
        if artifact_id:
            rows = [r for r in rows if str(r.get("artifact_id", "")) == artifact_id]
        if decision:
            want = str(decision).strip().lower()
            rows = [r for r in rows if str(r.get("decision", "")).strip().lower() == want]
        return {
            "run_id": entry.run_id,
            "pipeline_review_decisions": rows,
            "count": len(rows),
        }

    def append_pipeline_review_decision(
        self,
        *,
        run_id: str,
        artifact_type: str,
        artifact_id: str,
        decision: str,
        reviewer: str | None = None,
        reason: str = "",
        replacement_value: Any | None = None,
        evidence: list[str] | None = None,
        applies_to_field: str | None = None,
        supersedes_decision_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        decision_id: str | None = None,
    ) -> dict[str, Any]:
        """Append to ``pipeline_review_decisions.json`` for the resolved export bundle."""
        from .pipeline_reviews import append_pipeline_review_decision as append_decision

        self._resolve_run_entry(run_id)
        return append_decision(
            self.export_dir,
            run_id=run_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            decision=decision,
            reviewer=reviewer,
            reason=reason,
            replacement_value=replacement_value,
            evidence=evidence,
            applies_to_field=applies_to_field,
            supersedes_decision_id=supersedes_decision_id,
            metadata=metadata,
            decision_id=decision_id,
        )

    def list_source_records(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        records = self._artifact_list(entry=entry, artifact_type="source_records")
        cleaned: list[dict[str, Any]] = []
        for row in records:
            out = dict(row)
            out.pop("_summary_only", None)
            cleaned.append(out)
        return {"run_id": entry.run_id, "source_records": cleaned}

    def list_source_target_links(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        links = self._artifact_list(entry=entry, artifact_type="source_target_links")
        return {"run_id": entry.run_id, "source_target_links": links}

    def list_source_categorisation_rationales(
        self,
        run_id: str | None = None,
        *,
        source_record_id: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        rows = self._artifact_list(
            entry=entry, artifact_type="source_categorisation_rationales"
        )
        if source_record_id:
            rows = [
                item
                for item in rows
                if str(item.get("source_record_id", "")) == str(source_record_id)
            ]
        return {"run_id": entry.run_id, "source_categorisation_rationales": rows}

    def list_effective_source_target_links(
        self,
        run_id: str | None = None,
        *,
        source_record_id: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        decisions = self._artifact_list(entry=entry, artifact_type="pipeline_review_decisions")
        links = self._artifact_list(entry=entry, artifact_type="source_target_links")
        if source_record_id:
            links = [
                item
                for item in links
                if str(item.get("source_record_id", "")) == str(source_record_id)
            ]
        views = [
            resolve_effective_artifact_view(
                artifact_type="source_target_link",
                original_artifact=item,
                pipeline_review_decisions=decisions,
            )
            for item in links
        ]
        return {"run_id": entry.run_id, "effective_source_target_links": views, "count": len(views)}

    def list_effective_source_categorisation_rationales(
        self,
        run_id: str | None = None,
        *,
        source_record_id: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        decisions = self._artifact_list(entry=entry, artifact_type="pipeline_review_decisions")
        rows = self._artifact_list(
            entry=entry, artifact_type="source_categorisation_rationales"
        )
        if source_record_id:
            rows = [
                item
                for item in rows
                if str(item.get("source_record_id", "")) == str(source_record_id)
            ]
        views = [
            resolve_effective_artifact_view(
                artifact_type="source_categorisation_rationale",
                original_artifact=item,
                pipeline_review_decisions=decisions,
            )
            for item in rows
        ]
        return {
            "run_id": entry.run_id,
            "effective_source_categorisation_rationales": views,
            "count": len(views),
        }

    def list_effective_proposition_extraction_traces(
        self,
        *,
        run_id: str | None = None,
        proposition_id: str | None = None,
        source_record_id: str | None = None,
        source_fragment_id: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        decisions = self._artifact_list(entry=entry, artifact_type="pipeline_review_decisions")
        traces = self._artifact_list(
            entry=entry, artifact_type="proposition_extraction_traces"
        )
        if proposition_id:
            traces = [
                item
                for item in traces
                if str(item.get("proposition_id", "")) == str(proposition_id)
            ]
        if source_record_id:
            traces = [
                item
                for item in traces
                if str(item.get("source_record_id", "")) == str(source_record_id)
            ]
        if source_fragment_id:
            traces = [
                item
                for item in traces
                if str(item.get("source_fragment_id", "")) == str(source_fragment_id)
            ]
        views = [
            resolve_effective_artifact_view(
                artifact_type="proposition_extraction_trace",
                original_artifact=item,
                pipeline_review_decisions=decisions,
            )
            for item in traces
        ]
        return {
            "run_id": entry.run_id,
            "effective_proposition_extraction_traces": views,
            "count": len(views),
        }

    def list_effective_propositions(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        decisions = self._artifact_list(entry=entry, artifact_type="pipeline_review_decisions")
        propositions = self._artifact_list(entry=entry, artifact_type="propositions")
        views = [
            resolve_effective_artifact_view(
                artifact_type="proposition",
                original_artifact=item,
                pipeline_review_decisions=decisions,
            )
            for item in propositions
        ]
        return {"run_id": entry.run_id, "effective_propositions": views, "count": len(views)}

    def _build_proposition_explorer_bundle(self, entry: RunIndexEntry) -> dict[str, Any]:
        """Single load of review-backed proposition rows, traces, links, and indexes (per request)."""
        decisions = self._artifact_list(entry=entry, artifact_type="pipeline_review_decisions")
        propositions = self._artifact_list(entry=entry, artifact_type="propositions")
        prop_views = [
            resolve_effective_artifact_view(
                artifact_type="proposition",
                original_artifact=item,
                pipeline_review_decisions=decisions,
            )
            for item in propositions
        ]
        links = self._artifact_list(entry=entry, artifact_type="proposition_scope_links")
        scopes = self._artifact_list(entry=entry, artifact_type="legal_scopes")
        sources_payload = self.list_source_records(run_id=entry.run_id)
        sources: list[dict[str, Any]] = list(sources_payload.get("source_records") or [])
        traces = self._artifact_list(entry=entry, artifact_type="proposition_extraction_traces")
        trace_views = [
            resolve_effective_artifact_view(
                artifact_type="proposition_extraction_trace",
                original_artifact=item,
                pipeline_review_decisions=decisions,
            )
            for item in traces
        ]
        completeness_rows = self._artifact_list(
            entry=entry, artifact_type="proposition_completeness_assessments"
        )

        scope_by_id: dict[str, dict[str, Any]] = {}
        for s in scopes:
            sid = str(s.get("id") or "").strip()
            if sid:
                scope_by_id[sid] = s

        links_by_prop: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ln in links:
            pid = str(ln.get("proposition_id") or "").strip()
            if pid:
                links_by_prop[pid].append(ln)

        trace_by_prop: dict[str, dict[str, Any]] = {}
        for tv in sorted(trace_views, key=lambda x: str(x.get("artifact_id") or "")):
            oa = tv.get("original_artifact")
            if not isinstance(oa, dict):
                continue
            pid = str(oa.get("proposition_id") or "").strip()
            if pid and pid not in trace_by_prop:
                trace_by_prop[pid] = tv

        completeness_by_prop: dict[str, dict[str, Any]] = {}
        for row in completeness_rows:
            pid = str(row.get("proposition_id") or "").strip()
            if pid:
                completeness_by_prop[pid] = row

        prop_by_id: dict[str, dict[str, Any]] = {}
        for pv in prop_views:
            oa = pv.get("original_artifact")
            if isinstance(oa, dict):
                pid = str(oa.get("id") or "").strip()
                if pid:
                    prop_by_id[pid] = pv

        return {
            "run_id": entry.run_id,
            "decisions": decisions,
            "prop_views": prop_views,
            "links": links,
            "scopes": scopes,
            "sources": sources,
            "scope_by_id": scope_by_id,
            "links_by_prop": dict(links_by_prop),
            "trace_by_prop": trace_by_prop,
            "completeness_by_prop": completeness_by_prop,
            "prop_by_id": prop_by_id,
            "trace_views": trace_views,
            "completeness_rows": completeness_rows,
            "pipeline_review_decisions": decisions,
        }

    @staticmethod
    def _trace_confidence(row: dict[str, Any], trace_by_prop: dict[str, dict[str, Any]]) -> str:
        oa = row.get("original_artifact")
        if not isinstance(oa, dict):
            return ""
        pid = str(oa.get("id") or "").strip()
        tr = trace_by_prop.get(pid)
        if not tr:
            return ""
        ev = tr.get("effective_value")
        if not isinstance(ev, dict):
            return ""
        return str(ev.get("confidence") or "").strip()

    @staticmethod
    def _proposition_display_label_short(row: dict[str, Any]) -> str:
        oa = row.get("original_artifact")
        if not isinstance(oa, dict):
            oa = {}
        text = str(oa.get("proposition_text") or "").strip()
        if text:
            return text if len(text) <= 220 else f"{text[:216]}…"
        loc = str(oa.get("fragment_locator") or "").strip()
        if loc:
            return loc if len(loc) <= 160 else f"{loc[:156]}…"
        pk = str(oa.get("proposition_key") or "").strip()
        return pk or str(oa.get("id") or "") or "—"

    def _explorer_filter_proposition_rows(
        self,
        bundle: dict[str, Any],
        *,
        scope: str | None,
        source_id: str | None,
        review_status: str | None,
        confidence: str | None,
        search: str | None,
        instrument_family: str | None,
    ) -> list[dict[str, Any]]:
        prop_views: list[dict[str, Any]] = bundle["prop_views"]
        links: list[dict[str, Any]] = bundle["links"]
        scope_by_id: dict[str, dict[str, Any]] = bundle["scope_by_id"]
        trace_by_prop: dict[str, dict[str, Any]] = bundle["trace_by_prop"]
        sources: list[dict[str, Any]] = bundle["sources"]

        scope_tok = (scope or "").strip()
        rev_want = (review_status or "").strip().lower()
        conf_want = (confidence or "").strip()
        fam_want = (instrument_family or "").strip()
        src_sel = (source_id or "").strip()

        rows: list[dict[str, Any]] = []
        for row in prop_views:
            oa = row.get("original_artifact")
            if not isinstance(oa, dict):
                continue
            pid = str(oa.get("id") or "").strip()
            if scope_tok and not peg.proposition_matches_primary_visible_scope_filter(
                pid, scope_tok, links, scope_by_id
            ):
                continue
            if conf_want and self._trace_confidence(row, trace_by_prop) != conf_want:
                continue
            review = str(row.get("effective_status") or "").strip().lower()
            if rev_want and review != rev_want:
                continue
            if fam_want and peg.source_instrument_family_key_for_row(row, sources) != fam_want:
                continue
            rows.append(row)

        if src_sel:
            touch: set[str] = set()
            for row in rows:
                oa = row.get("original_artifact")
                if not isinstance(oa, dict):
                    continue
                if str(oa.get("source_record_id") or "").strip() == src_sel:
                    touch.add(peg.group_key_for_proposition_row(row, sources))
            rows = [r for r in rows if peg.group_key_for_proposition_row(r, sources) in touch]

        q = (search or "").strip()
        if q:
            rows = [r for r in rows if peg.proposition_row_matches_search(r, q)]

        return rows

    def _primary_scope_slugs_for_group(
        self,
        rows: list[dict[str, Any]],
        links_by_prop: dict[str, list[dict[str, Any]]],
        scope_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            oa = row.get("original_artifact")
            if not isinstance(oa, dict):
                continue
            pid = str(oa.get("id") or "").strip()
            if not pid:
                continue
            for ln in links_by_prop.get(pid) or []:
                if not peg.is_primary_scope_link_row(ln):
                    continue
                sco = str(ln.get("scope_id") or "").strip()
                sc = scope_by_id.get(sco)
                slug = str(sc.get("slug") or sco) if isinstance(sc, dict) else sco
                if slug and slug not in seen:
                    seen.add(slug)
                    ordered.append(slug)
        return ordered

    def _group_review_summary(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            st = str(row.get("effective_status") or "").strip().lower() or "unknown"
            counts[st] = counts.get(st, 0) + 1
        return counts

    def _group_wording_status(self, rows: list[dict[str, Any]]) -> str:
        if len(rows) <= 1:
            return "single"
        fps: set[str] = set()
        for row in rows:
            oa = row.get("original_artifact")
            if not isinstance(oa, dict):
                oa = {}
            fps.add(peg.wording_fingerprint_for_proposition_group_compare(oa))
        return "same" if len(fps) <= 1 else "diff"

    def _group_completeness_status(self, rows: list[dict[str, Any]], comp_by: dict[str, dict[str, Any]]) -> str | None:
        for row in rows:
            oa = row.get("original_artifact")
            if not isinstance(oa, dict):
                continue
            pid = str(oa.get("id") or "").strip()
            crow = comp_by.get(pid)
            if crow and isinstance(crow.get("status"), str):
                return str(crow["status"])
        return None

    def list_proposition_groups(
        self,
        *,
        run_id: str | None = None,
        scope: str | None = None,
        source_id: str | None = None,
        review_status: str | None = None,
        confidence: str | None = None,
        article: str | None = None,
        search: str | None = None,
        instrument_family: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_debug: bool = False,
        include_coarse_parent_rows: bool = False,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        bundle = self._build_proposition_explorer_bundle(entry)
        sources: list[dict[str, Any]] = bundle["sources"]
        links_by_prop: dict[str, list[dict[str, Any]]] = bundle["links_by_prop"]
        scope_by_id: dict[str, dict[str, Any]] = bundle["scope_by_id"]
        comp_by: dict[str, dict[str, Any]] = bundle["completeness_by_prop"]

        matching = self._explorer_filter_proposition_rows(
            bundle,
            scope=scope,
            source_id=source_id,
            review_status=review_status,
            confidence=confidence,
            search=search,
            instrument_family=instrument_family,
        )
        universe = list(matching)
        if include_coarse_parent_rows:
            filtered = universe
        else:
            filtered = [
                r
                for r in universe
                if not peg.should_suppress_coarse_parent_proposition_in_default_view(r, universe)
            ]

        built = peg.build_proposition_groups_pipeline(
            filtered, sources, links_by_prop, scope_by_id
        )
        art_tok = (article or "").strip()
        if art_tok:
            built = [g for g in built if peg.article_filter_matches_group(art_tok, g)]
        sorted_groups = peg.sort_merged_groups_for_explorer(built, sources)
        total_groups = len(sorted_groups)
        total_rows = len(filtered)
        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)
        page = sorted_groups[safe_offset : safe_offset + safe_limit]

        fragments_raw = self._read_json_file(entry.run_dir / "source_fragments.json", default=[])
        heading_by_article_locator: dict[str, str] = {}
        if isinstance(fragments_raw, list):
            for frag in fragments_raw:
                if not isinstance(frag, dict):
                    continue
                loc = str(frag.get("locator") or "").strip().lower()
                heading = frag.get("structural_heading")
                if not isinstance(heading, dict):
                    continue
                text = " ".join(str(heading.get("text") or "").replace("\xa0", " ").split()).strip()
                if loc.startswith("article:") and loc.count(":") == 1 and text:
                    heading_by_article_locator[loc] = text

        groups_out: list[dict[str, Any]] = []
        for g in page:
            rows = list(g.get("rows") or [])
            if not rows:
                continue
            gkey = str(g.get("key") or "")
            ack = peg.article_cluster_key_from_row(rows[0])
            row_ids: list[str] = []
            for row in rows:
                oa = row.get("original_artifact")
                if isinstance(oa, dict):
                    pid = str(oa.get("id") or "").strip()
                    if pid:
                        row_ids.append(pid)
            fo0 = rows[0].get("original_artifact")
            first_oa = fo0 if isinstance(fo0, dict) else {}
            rep_sid = str(first_oa.get("source_record_id") or "").strip()
            scope_b = peg.scope_bucket_for_proposition_group(rows, links_by_prop, scope_by_id)
            item: dict[str, Any] = {
                "group_id": gkey,
                "article_key": ack,
                "article_heading": peg.format_article_cluster_display_heading(
                    ack,
                    legislative_heading=heading_by_article_locator.get(ack.lower()),
                ),
                "section_cluster_key": peg.explorer_section_cluster_key_from_row(rows[0], sources),
                "scope_nav_cluster_key": scope_b["clusterKey"],
                "scope_section_label": scope_b["label"],
                "representative_source_record_id": rep_sid,
                "display_label": self._proposition_display_label_short(rows[0]),
                "proposition_count": len(row_ids),
                "source_row_count": len(rows),
                "jurisdictions": peg.jurisdiction_labels_represented(rows, sources),
                "primary_scopes": self._primary_scope_slugs_for_group(
                    rows, links_by_prop, scope_by_id
                ),
                "completeness_status": self._group_completeness_status(rows, comp_by),
                "review_summary": self._group_review_summary(rows),
                "wording_status": self._group_wording_status(rows),
                "row_ids": row_ids,
            }
            if include_debug:
                item["merge_debug"] = g.get("mergeDebug")
            groups_out.append(item)

        return {
            "run_id": entry.run_id,
            "total_groups": total_groups,
            "total_rows": total_rows,
            "limit": safe_limit,
            "offset": safe_offset,
            "groups": groups_out,
        }

    def inspect_proposition_group_detail(
        self,
        group_id: str,
        *,
        run_id: str | None = None,
        scope: str | None = None,
        source_id: str | None = None,
        review_status: str | None = None,
        confidence: str | None = None,
        article: str | None = None,
        search: str | None = None,
        instrument_family: str | None = None,
        include_coarse_parent_rows: bool = False,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        bundle = self._build_proposition_explorer_bundle(entry)
        sources: list[dict[str, Any]] = bundle["sources"]
        links_by_prop: dict[str, list[dict[str, Any]]] = bundle["links_by_prop"]
        scope_by_id: dict[str, dict[str, Any]] = bundle["scope_by_id"]
        trace_by_prop: dict[str, dict[str, Any]] = bundle["trace_by_prop"]
        prd: list[dict[str, Any]] = bundle["pipeline_review_decisions"]

        matching = self._explorer_filter_proposition_rows(
            bundle,
            scope=scope,
            source_id=source_id,
            review_status=review_status,
            confidence=confidence,
            search=search,
            instrument_family=instrument_family,
        )
        universe = list(matching)
        if include_coarse_parent_rows:
            filtered = universe
        else:
            filtered = [
                r
                for r in universe
                if not peg.should_suppress_coarse_parent_proposition_in_default_view(r, universe)
            ]

        built = peg.build_proposition_groups_pipeline(
            filtered, sources, links_by_prop, scope_by_id
        )
        art_tok = (article or "").strip()
        if art_tok:
            built = [g for g in built if peg.article_filter_matches_group(art_tok, g)]

        hit = next((g for g in built if str(g.get("key") or "") == group_id), None)
        if not hit:
            raise OperationsError(f"Proposition group not found: {group_id!r}")

        rows: list[dict[str, Any]] = list(hit.get("rows") or [])
        row_ids: set[str] = set()
        trace_artifact_ids: set[str] = set()
        for row in rows:
            oa = row.get("original_artifact")
            if not isinstance(oa, dict):
                continue
            pid = str(oa.get("id") or "").strip()
            if pid:
                row_ids.add(pid)
            tr = trace_by_prop.get(pid or "")
            if tr:
                aid = str(tr.get("artifact_id") or "").strip()
                if aid:
                    trace_artifact_ids.add(aid)

        scope_links_out: list[dict[str, Any]] = []
        seen_links: set[tuple[str, str, str]] = set()
        for pid in sorted(row_ids):
            for ln in links_by_prop.get(pid) or []:
                key = (
                    str(ln.get("proposition_id") or ""),
                    str(ln.get("scope_id") or ""),
                    str(ln.get("id") or ""),
                )
                if key in seen_links:
                    continue
                seen_links.add(key)
                scope_links_out.append(ln)

        comp_out = [
            bundle["completeness_by_prop"][pid]
            for pid in sorted(row_ids)
            if pid in bundle["completeness_by_prop"]
        ]

        prd_out: list[dict[str, Any]] = []
        for d in prd:
            at = str(d.get("artifact_type") or "").strip()
            aid = str(d.get("artifact_id") or "").strip()
            if not aid:
                continue
            if at == "proposition" and aid in row_ids:
                prd_out.append(d)
            elif at == "proposition_extraction_trace" and aid in trace_artifact_ids:
                prd_out.append(d)

        trace_refs: list[dict[str, Any]] = []
        for pid in sorted(row_ids):
            tr = trace_by_prop.get(pid)
            if not tr:
                continue
            aid = str(tr.get("artifact_id") or "").strip()
            if aid:
                trace_refs.append(
                    {
                        "proposition_id": pid,
                        "artifact_id": aid,
                        "artifact_type": "proposition_extraction_trace",
                    }
                )

        return {
            "run_id": entry.run_id,
            "group_id": group_id,
            "effective_propositions": rows,
            "proposition_scope_links": scope_links_out,
            "legal_scopes": bundle["scopes"],
            "completeness_assessments": comp_out,
            "pipeline_review_decisions": prd_out,
            "extraction_trace_references": trace_refs,
            "merge_debug": hit.get("mergeDebug"),
        }

    def list_source_fetch_attempts(
        self,
        run_id: str | None = None,
        source_record_id: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        attempts = self._artifact_list(entry=entry, artifact_type="source_fetch_attempts")
        if source_record_id:
            attempts = [
                item
                for item in attempts
                if str(item.get("source_record_id", "")) == str(source_record_id)
            ]
        return {"run_id": entry.run_id, "source_fetch_attempts": attempts}

    def list_propositions(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        propositions = self._artifact_list(entry=entry, artifact_type="propositions")
        return {"run_id": entry.run_id, "propositions": propositions}

    def list_legal_scopes(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        scopes = self._artifact_list(entry=entry, artifact_type="legal_scopes")
        return {"run_id": entry.run_id, "legal_scopes": scopes, "count": len(scopes)}

    def list_proposition_scope_links(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        links = self._artifact_list(entry=entry, artifact_type="proposition_scope_links")
        return {"run_id": entry.run_id, "proposition_scope_links": links, "count": len(links)}

    def list_propositions_for_scope(
        self,
        scope_id: str,
        *,
        run_id: str | None = None,
        include_descendants: bool = True,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        scopes_raw = self._artifact_list(entry=entry, artifact_type="legal_scopes")
        links_raw = self._artifact_list(entry=entry, artifact_type="proposition_scope_links")
        propositions_raw = self._artifact_list(entry=entry, artifact_type="propositions")

        children_by_parent: dict[str, list[str]] = {}
        for scope in scopes_raw:
            pid = scope.get("parent_scope_id")
            if pid:
                children_by_parent.setdefault(str(pid), []).append(str(scope.get("id", "")))

        def descendants(root: str) -> set[str]:
            out: set[str] = {root}
            stack = [root]
            while stack:
                cur = stack.pop()
                for ch in children_by_parent.get(cur, []):
                    if ch and ch not in out:
                        out.add(ch)
                        stack.append(ch)
            return out

        want_ids = descendants(scope_id) if include_descendants else {scope_id}
        filtered_links = [
            ln
            for ln in links_raw
            if str(ln.get("scope_id", "")).strip() in want_ids
        ]
        prop_ids = {
            str(ln.get("proposition_id", "")).strip()
            for ln in filtered_links
            if str(ln.get("proposition_id", "")).strip()
        }
        prop_by_id = {
            str(p.get("id", "")): p
            for p in propositions_raw
            if str(p.get("id", "")).strip()
        }
        props_out = [prop_by_id[pid] for pid in sorted(prop_ids) if pid in prop_by_id]

        return {
            "run_id": entry.run_id,
            "scope_id": scope_id,
            "include_descendants": include_descendants,
            "allowed_scope_ids": sorted(want_ids),
            "proposition_scope_links": filtered_links,
            "propositions": props_out,
            "link_count": len(filtered_links),
            "proposition_count": len(props_out),
        }

    def list_proposition_extraction_traces(
        self,
        *,
        run_id: str | None = None,
        proposition_id: str | None = None,
        source_record_id: str | None = None,
        source_fragment_id: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        traces = self._artifact_list(
            entry=entry, artifact_type="proposition_extraction_traces"
        )
        if proposition_id:
            traces = [
                item
                for item in traces
                if str(item.get("proposition_id", "")) == str(proposition_id)
            ]
        if source_record_id:
            traces = [
                item
                for item in traces
                if str(item.get("source_record_id", "")) == str(source_record_id)
            ]
        if source_fragment_id:
            traces = [
                item
                for item in traces
                if str(item.get("source_fragment_id", "")) == str(source_fragment_id)
            ]
        return {"run_id": entry.run_id, "proposition_extraction_traces": traces}

    def list_proposition_completeness_assessments(
        self,
        *,
        run_id: str | None = None,
        proposition_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        rows = self._artifact_list(
            entry=entry, artifact_type="proposition_completeness_assessments"
        )
        if proposition_id:
            rows = [
                item
                for item in rows
                if str(item.get("proposition_id", "")) == str(proposition_id)
            ]
        if status:
            rows = [item for item in rows if str(item.get("status", "")) == str(status)]
        return {"run_id": entry.run_id, "proposition_completeness_assessments": rows}

    def list_divergence_assessments(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        assessments = self._artifact_list(entry=entry, artifact_type="divergence_assessments")
        return {"run_id": entry.run_id, "divergence_assessments": assessments}

    def resolve_run_export_dir(self, run_id: str) -> Path:
        """Absolute path to the on-disk export root for a run (``runs/{run_id}/``)."""
        entry = self._resolve_run_entry(run_id)
        return entry.run_dir.resolve()

    def _bundle_for_repairable_extraction_metrics(self, entry: RunIndexEntry) -> dict[str, Any]:
        """Assemble bundle fields stored under artifacts / export root for repair scanning."""
        traces = self._artifact_list(entry=entry, artifact_type="proposition_extraction_traces")
        propositions = self._artifact_list(entry=entry, artifact_type="propositions")
        failures = self._artifact_list(entry=entry, artifact_type="proposition_extraction_failures")
        bundle: dict[str, Any] = {
            "run": entry.run_payload,
            "proposition_extraction_traces": traces,
            "propositions": propositions,
            "proposition_extraction_failures": failures,
        }
        llm_root = self._read_json_file(self.export_dir / "extraction_llm_call_traces.json", None)
        if isinstance(llm_root, list):
            bundle["extraction_llm_call_traces"] = llm_root
        root_run = self._read_json_file(self.export_dir / "run.json", default={})
        root_rid = str((root_run or {}).get("id") or "") if isinstance(root_run, dict) else ""
        if root_rid == entry.run_id:
            if not traces:
                root_tr = self._read_json_file(
                    self.export_dir / "proposition_extraction_traces.json", default=None
                )
                if isinstance(root_tr, list):
                    bundle["proposition_extraction_traces"] = root_tr
            if not propositions:
                root_p = self._read_json_file(self.export_dir / "propositions.json", default=None)
                if isinstance(root_p, list):
                    bundle["propositions"] = root_p
            if not failures:
                root_f = self._read_json_file(
                    self.export_dir / "proposition_extraction_failures.json", default=None
                )
                if isinstance(root_f, list):
                    bundle["proposition_extraction_failures"] = root_f
        return bundle

    def read_run_quality_summary(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        root_path = self.export_dir / "run_quality_summary.json"
        summary: dict[str, Any] | None = None
        if root_path.exists():
            root_summary = self._read_json_file(root_path, default={})
            if (
                isinstance(root_summary, dict)
                and str(root_summary.get("run_id", "")) == entry.run_id
            ):
                summary = dict(root_summary)

        if summary is None:
            payload = self._artifact_payload(
                entry=entry, artifact_type="run_quality_summary", default={}
            )
            if isinstance(payload, dict) and str(payload.get("run_id", "")) == entry.run_id:
                summary = dict(payload)

        if summary is None:
            raise OperationsError(
                "Run quality summary is not available for this export (pre-summary bundle)."
            )

        from law_proposition_extractor_pipeline.extraction_repair import repairable_extraction_metrics_from_bundle

        bundle = self._bundle_for_repairable_extraction_metrics(entry)
        metrics_raw = summary.get("metrics")
        metrics = dict(metrics_raw) if isinstance(metrics_raw, dict) else {}
        metrics["repairable_extraction"] = repairable_extraction_metrics_from_bundle(bundle)
        summary["metrics"] = metrics

        return {"run_id": entry.run_id, "run_quality_summary": summary}

    def _read_run_scoped_export_object(
        self,
        *,
        entry: RunIndexEntry,
        root_filename: str,
        artifact_type: str,
    ) -> dict[str, Any] | None:
        root_path = self.export_dir / root_filename
        if root_path.is_file():
            root_payload = self._read_json_file(root_path, default={})
            if isinstance(root_payload, dict) and str(root_payload.get("run_id", "")) == entry.run_id:
                return dict(root_payload)

        payload = self._artifact_payload(entry=entry, artifact_type=artifact_type, default={})
        if isinstance(payload, dict) and str(payload.get("run_id", "")) == entry.run_id:
            return dict(payload)
        return None

    def read_effective_law_statements(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        payload = self._read_run_scoped_export_object(
            entry=entry,
            root_filename="effective_law_statements.json",
            artifact_type="effective_law_statements",
        )
        if payload is None:
            raise OperationsError(
                "Effective law statements are not available for this export "
                "(expected effective_law_statements.json)."
            )
        statements = payload.get("statements")
        statement_rows = [row for row in statements if isinstance(row, dict)] if isinstance(statements, list) else []
        return {
            "run_id": entry.run_id,
            "effective_law_statements": payload,
            "statement_count": len(statement_rows),
        }

    def read_proposition_matcher_law_candidates(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        payload = self._read_run_scoped_export_object(
            entry=entry,
            root_filename="proposition_matcher_law_candidates.json",
            # readers also accept beatrice_law_candidates.json (COMPAT_LEGACY_NAME),
            artifact_type="proposition_matcher_law_candidates",
        )
        if payload is None:
            raise OperationsError(
                "Proposition Matcher law candidates are not available for this export "
                "(expected proposition_matcher_law_candidates.json)."
            )
        candidates = payload.get("candidates")
        candidate_rows = [row for row in candidates if isinstance(row, dict)] if isinstance(candidates, list) else []
        return {
            "run_id": entry.run_id,
            "proposition_matcher_law_candidates": payload,
            "candidate_count": len(candidate_rows),
        }

    def read_source_legal_effects(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        payload = self._read_run_scoped_export_object(
            entry=entry,
            root_filename="source_legal_effects.json",
            artifact_type="source_legal_effects",
        )
        if payload is None:
            # Older exports without the artifact remain loadable.
            return {
                "run_id": entry.run_id,
                "source_legal_effects": {
                    "schema_version": "1",
                    "run_id": entry.run_id,
                    "effects": [],
                    "effect_links": [],
                    "outstanding_effects_status": "source_status_unknown",
                    "diagnostics": [],
                    "metadata": {"missing_artifact": True},
                },
                "effect_count": 0,
                "effect_link_count": 0,
                "artifact_present": False,
            }
        effects = payload.get("effects")
        links = payload.get("effect_links")
        effect_rows = [row for row in effects if isinstance(row, dict)] if isinstance(effects, list) else []
        link_rows = [row for row in links if isinstance(row, dict)] if isinstance(links, list) else []
        return {
            "run_id": entry.run_id,
            "source_legal_effects": payload,
            "effect_count": len(effect_rows),
            "effect_link_count": len(link_rows),
            "artifact_present": True,
        }

    def read_decision_explanations(self, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        payload = self._read_run_scoped_export_object(
            entry=entry,
            root_filename="decision_explanations.json",
            artifact_type="decision_explanations",
        )
        if payload is None:
            # Older exports without the artifact remain loadable.
            return {
                "run_id": entry.run_id,
                "decision_explanations": {
                    "schema_version": "1",
                    "run_id": entry.run_id,
                    "decisions": [],
                    "metadata": {"missing_artifact": True},
                },
                "decision_count": 0,
                "artifact_present": False,
            }
        decisions = payload.get("decisions")
        decision_rows = (
            [row for row in decisions if isinstance(row, dict)]
            if isinstance(decisions, list)
            else []
        )
        return {
            "run_id": entry.run_id,
            "decision_explanations": payload,
            "decision_count": len(decision_rows),
            "artifact_present": True,
        }

    def list_heuristic_definitions(
        self,
        *,
        run_id: str | None = None,
        referenced_only: bool = False,
    ) -> dict[str, Any]:
        """Return code-declared heuristic registry definitions (no heuristic execution).

        When ``referenced_only`` is true, restrict to rule_ids referenced by the
        active run's ``decision_explanations`` artifact (including soft-missing
        empty artifacts → empty list). Absolute filesystem paths are never
        included; ``code_references`` remain module-qualified symbols only.
        """
        from law_proposition_extractor_pipeline.heuristics.registry import REGISTRY_VERSION, list_heuristics

        referenced_ids: set[str] | None = None
        resolved_run_id: str | None = None
        if referenced_only:
            decision_payload = self.read_decision_explanations(run_id=run_id)
            resolved_run_id = str(decision_payload.get("run_id") or "") or None
            artifact = decision_payload.get("decision_explanations")
            referenced_ids = set()
            if isinstance(artifact, dict):
                metadata = artifact.get("metadata")
                if isinstance(metadata, dict):
                    for row in metadata.get("referenced_rules") or []:
                        if isinstance(row, dict):
                            rid = str(row.get("rule_id") or "").strip()
                            if rid:
                                referenced_ids.add(rid)
                for decision in artifact.get("decisions") or []:
                    if isinstance(decision, dict):
                        rid = str(decision.get("rule_id") or "").strip()
                        if rid:
                            referenced_ids.add(rid)
        elif run_id is not None:
            entry = self._resolve_run_entry(run_id)
            resolved_run_id = entry.run_id

        heuristics: list[dict[str, Any]] = []
        for definition in list_heuristics():
            if referenced_ids is not None and definition.rule_id not in referenced_ids:
                continue
            heuristics.append(
                {
                    "rule_id": definition.rule_id,
                    "version": definition.version,
                    "name": definition.name,
                    "plain_english_summary": definition.plain_english_summary,
                    "stage": definition.stage.value
                    if hasattr(definition.stage, "value")
                    else str(definition.stage),
                    "method": definition.method.value
                    if hasattr(definition.method, "value")
                    else str(definition.method),
                    "input_kinds": list(definition.input_kinds),
                    "output_kinds": list(definition.output_kinds),
                    "trigger_summary": definition.trigger_summary,
                    "precedence_summary": definition.precedence_summary,
                    "failure_mode": definition.failure_mode,
                    "diagnostic_codes": list(definition.diagnostic_codes),
                    "code_references": list(definition.code_references),
                    "test_references": list(definition.test_references),
                    "example_summary": definition.example_summary,
                }
            )

        return {
            "registry_version": REGISTRY_VERSION,
            "run_id": resolved_run_id,
            "referenced_only": bool(referenced_only),
            "heuristic_count": len(heuristics),
            "heuristics": heuristics,
        }

    def get_source_detail(self, source_id: str, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        merged_raw = self._merged_source_records_for_run(entry)
        want = source_id.strip()
        source = next(
            (item for item in merged_raw if self._source_record_row_id(item) == want),
            None,
        )
        if source is None:
            raise OperationsError(f"Source record {source_id!r} was not found.")

        source_out = dict(source)
        summary_only = bool(source_out.pop("_summary_only", False))

        snapshots_payload = self.list_source_snapshots(source_id=want, run_id=entry.run_id)
        snapshots_raw = snapshots_payload.get("source_snapshots")
        snapshots = snapshots_raw if isinstance(snapshots_raw, list) else []

        fragments_payload = self.list_source_fragments(source_id=want, run_id=entry.run_id)
        fragments_raw = fragments_payload.get("source_fragments")
        fragments = fragments_raw if isinstance(fragments_raw, list) else []

        parse_payload = self.list_source_parse_traces(
            run_id=entry.run_id,
            source_record_id=want,
        )
        parse_raw = parse_payload.get("source_parse_traces")
        parse_traces = parse_raw if isinstance(parse_raw, list) else []

        fetch_payload = self.list_source_fetch_attempts(
            run_id=entry.run_id,
            source_record_id=want,
        )
        fetch_raw = fetch_payload.get("source_fetch_attempts")
        fetch_attempts = fetch_raw if isinstance(fetch_raw, list) else []

        current_snapshot_id = str(source.get("current_snapshot_id") or "")
        current_snapshot: dict[str, Any] | None = None
        if current_snapshot_id:
            for snap in snapshots:
                if isinstance(snap, dict) and str(snap.get("id")) == current_snapshot_id:
                    current_snapshot = snap
                    break

        partial = summary_only or (not snapshots and not fragments)

        return {
            "run_id": entry.run_id,
            "source_id": want,
            "partial": partial,
            "source_record": source_out,
            "current_snapshot": current_snapshot,
            "source_snapshots": snapshots,
            "source_fragments": fragments,
            "source_parse_traces": parse_traces,
            "source_fetch_attempts": fetch_attempts,
        }

    def inspect_source_record(self, source_id: str, run_id: str | None = None) -> dict[str, Any]:
        return self.get_source_detail(source_id=source_id, run_id=run_id)

    def list_source_snapshots(self, source_id: str, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        snapshots_raw = self._artifact_list(entry=entry, artifact_type="source_snapshots")
        snapshots = [
            item for item in snapshots_raw if str(item.get("source_record_id", "")) == source_id
        ]
        return {"run_id": entry.run_id, "source_id": source_id, "source_snapshots": snapshots}

    def list_all_source_snapshots(
        self,
        run_id: str | None = None,
        *,
        include_authoritative_text: bool = False,
    ) -> dict[str, Any]:
        """Return every source snapshot for a run (Workbench provenance join).

        By default omits ``authoritative_text`` to keep list payloads small; use
        ``get_source_snapshot_content`` for safe inspection of persisted text.
        Never resolves or serves ``raw_artifact_uri`` filesystem paths.
        """
        entry = self._resolve_run_entry(run_id)
        snapshots_raw = self._artifact_list(entry=entry, artifact_type="source_snapshots")
        cleaned: list[dict[str, Any]] = []
        for item in snapshots_raw:
            out = dict(item)
            text = out.get("authoritative_text")
            has_text = isinstance(text, str) and bool(text.strip())
            out["has_authoritative_text"] = has_text
            if not include_authoritative_text:
                out.pop("authoritative_text", None)
            cleaned.append(out)
        return {"run_id": entry.run_id, "source_snapshots": cleaned}

    def get_source_snapshot_content(
        self,
        snapshot_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Serve persisted snapshot text for a registered snapshot id only.

        Resolves content from the run's ``source_snapshots`` artifact. Does not
        accept filesystem paths from the client and does not open ``raw_artifact_uri``.
        """
        want = str(snapshot_id or "").strip()
        if not want:
            raise ValueError("snapshot_id must be a non-empty string.")
        entry = self._resolve_run_entry(run_id)
        snapshots_raw = self._artifact_list(entry=entry, artifact_type="source_snapshots")
        for item in snapshots_raw:
            if str(item.get("id", "")).strip() != want:
                continue
            text = item.get("authoritative_text")
            if not isinstance(text, str) or not text.strip():
                return {
                    "run_id": entry.run_id,
                    "snapshot_id": want,
                    "available": False,
                    "reason": "Full consumed snapshot text is not available from this run.",
                    "content": None,
                    "content_type": None,
                    "content_hash": item.get("content_hash"),
                    "parser_name": item.get("parser_name"),
                    "source_record_id": item.get("source_record_id"),
                }
            parser_name = str(item.get("parser_name") or "")
            content_type = (
                "application/xml"
                if "xml" in parser_name.lower() or parser_name.endswith("_xml_v1")
                else "text/plain"
            )
            return {
                "run_id": entry.run_id,
                "snapshot_id": want,
                "available": True,
                "reason": None,
                "content": text,
                "content_type": content_type,
                "content_hash": item.get("content_hash"),
                "parser_name": item.get("parser_name"),
                "source_record_id": item.get("source_record_id"),
            }
        raise OperationsError(f"Source snapshot {want!r} was not found.")

    def list_source_fragments(self, source_id: str, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        fragments_raw = self._artifact_list(entry=entry, artifact_type="source_fragments")
        fragments = [
            item for item in fragments_raw if str(item.get("source_record_id", "")) == source_id
        ]
        return {"run_id": entry.run_id, "source_id": source_id, "source_fragments": fragments}

    def list_source_fragments_filtered(
        self,
        *,
        run_id: str | None = None,
        source_record_id: str | None = None,
        source_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        fragments = self._artifact_list(entry=entry, artifact_type="source_fragments")
        if source_record_id:
            fragments = [
                item
                for item in fragments
                if str(item.get("source_record_id", "")) == str(source_record_id)
            ]
        if source_snapshot_id:
            fragments = [
                item
                for item in fragments
                if str(item.get("source_snapshot_id", "")) == str(source_snapshot_id)
            ]
        return {"run_id": entry.run_id, "source_fragments": fragments}

    def list_source_parse_traces(
        self,
        *,
        run_id: str | None = None,
        source_record_id: str | None = None,
        source_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        parse_traces = self._artifact_list(entry=entry, artifact_type="source_parse_traces")
        if source_record_id:
            parse_traces = [
                item
                for item in parse_traces
                if str(item.get("source_record_id", "")) == str(source_record_id)
            ]
        if source_snapshot_id:
            parse_traces = [
                item
                for item in parse_traces
                if str(item.get("source_snapshot_id", "")) == str(source_snapshot_id)
            ]
        return {"run_id": entry.run_id, "source_parse_traces": parse_traces}

    def source_snapshot_timeline(self, source_id: str, run_id: str | None = None) -> dict[str, Any]:
        entry = self._resolve_run_entry(run_id)
        snapshots_payload = self.list_source_snapshots(source_id=source_id, run_id=entry.run_id)
        snapshots = snapshots_payload.get("source_snapshots", [])
        if not isinstance(snapshots, list):
            snapshots = []
        timeline = self._build_timeline_events(
            source_id=source_id,
            snapshots=[item for item in snapshots if isinstance(item, dict)],
        )
        return {
            "run_id": entry.run_id,
            "source_id": source_id,
            "timepoint_count": len(timeline),
            "timepoints": timeline,
        }

    def source_snapshot_history(
        self,
        source_id: str,
        *,
        include_runs: bool = True,
        include_registry: bool = True,
    ) -> dict[str, Any]:
        event_by_id: dict[str, dict[str, Any]] = {}
        run_ids_scanned: list[str] = []
        registry_ids_matched: list[str] = []
        snapshot_lookup_by_id: dict[str, dict[str, Any]] = {}
        snapshot_lookup_by_hash: dict[str, dict[str, Any]] = {}

        if include_runs:
            for entry in self._run_index():
                run_ids_scanned.append(entry.run_id)
                snapshots = self._artifact_list(entry=entry, artifact_type="source_snapshots")
                for snapshot in snapshots:
                    if str(snapshot.get("source_record_id", "")) != source_id:
                        continue
                    self._upsert_history_event(
                        event_by_id=event_by_id,
                        snapshot=snapshot,
                        origin={"kind": "run_snapshot", "run_id": entry.run_id},
                    )
                    snapshot_id = str(snapshot.get("id", ""))
                    content_hash = str(snapshot.get("content_hash", ""))
                    if snapshot_id:
                        snapshot_lookup_by_id[snapshot_id] = snapshot
                    if content_hash:
                        snapshot_lookup_by_hash[content_hash] = snapshot

        if include_registry:
            for registry_entry in self._registry_entries():
                registry_id = str(registry_entry.get("registry_id", ""))
                current_state = registry_entry.get("current_state")
                if not isinstance(current_state, dict):
                    continue
                source_record = current_state.get("source_record")
                if not isinstance(source_record, dict):
                    continue
                if str(source_record.get("id", "")) != source_id:
                    continue

                if registry_id and registry_id not in registry_ids_matched:
                    registry_ids_matched.append(registry_id)

                current_snapshot = current_state.get("source_snapshot")
                if isinstance(current_snapshot, dict):
                    self._upsert_history_event(
                        event_by_id=event_by_id,
                        snapshot=current_snapshot,
                        origin={"kind": "registry_current_state", "registry_id": registry_id},
                    )
                    current_snapshot_id = str(current_snapshot.get("id", ""))
                    current_content_hash = str(current_snapshot.get("content_hash", ""))
                    if current_snapshot_id:
                        snapshot_lookup_by_id[current_snapshot_id] = current_snapshot
                    if current_content_hash:
                        snapshot_lookup_by_hash[current_content_hash] = current_snapshot

                refresh_history = registry_entry.get("refresh_history")
                if isinstance(refresh_history, list):
                    for history_item in refresh_history:
                        if not isinstance(history_item, dict):
                            continue
                        if str(history_item.get("source_record_id", "")) != source_id:
                            continue
                        history_snapshot_id = str(history_item.get("source_snapshot_id", ""))
                        history_content_hash = str(history_item.get("content_hash", ""))
                        reference_snapshot = snapshot_lookup_by_id.get(
                            history_snapshot_id
                        ) or snapshot_lookup_by_hash.get(history_content_hash)
                        pseudo_snapshot = self._registry_refresh_snapshot(
                            source_id=source_id,
                            history_item=history_item,
                            reference_snapshot=reference_snapshot,
                            registry_id=registry_id,
                        )
                        self._upsert_history_event(
                            event_by_id=event_by_id,
                            snapshot=pseudo_snapshot,
                            origin={
                                "kind": "registry_refresh",
                                "registry_id": registry_id,
                                "refreshed_at": history_item.get("refreshed_at"),
                            },
                        )

        timeline = self._build_timeline_events(
            source_id=source_id,
            snapshots=[item.get("snapshot", {}) for item in event_by_id.values()],
            extra_by_event_id={
                event_id: {"origins": item.get("origins", [])}
                for event_id, item in event_by_id.items()
            },
        )

        return {
            "source_id": source_id,
            "scope": "aggregated_history",
            "include_runs": include_runs,
            "include_registry": include_registry,
            "run_ids_scanned": sorted(run_ids_scanned),
            "registry_ids_matched": sorted(registry_ids_matched),
            "timepoint_count": len(timeline),
            "timepoints": timeline,
        }

    def proposition_history(
        self,
        proposition_key: str,
        *,
        include_runs: bool = True,
    ) -> dict[str, Any]:
        normalized_key = proposition_key.strip()
        if not normalized_key:
            raise OperationsError("proposition_key must be a non-empty string.")

        run_ids_scanned: list[str] = []
        observed_versions: list[dict[str, Any]] = []
        seen_observation_ids: set[str] = set()

        if include_runs:
            entries = self._run_index()
            for entry in entries:
                run_ids_scanned.append(entry.run_id)
                propositions = self._artifact_list(entry=entry, artifact_type="propositions")
                for proposition in propositions:
                    if str(proposition.get("proposition_key", "")) != normalized_key:
                        continue
                    observation = self._build_proposition_observation(
                        proposition=proposition,
                        fallback_run_id=entry.run_id,
                        fallback_run_created_at=entry.run_payload.get("created_at"),
                    )
                    observation_id = self._proposition_observation_id(observation=observation)
                    if observation_id in seen_observation_ids:
                        continue
                    seen_observation_ids.add(observation_id)
                    observed_versions.append(observation)

        if not observed_versions:
            raise OperationsError(
                f"Proposition key {normalized_key!r} was not found in exported runs."
            )

        ordered_versions = sorted(
            observed_versions,
            key=lambda item: (
                self._safe_datetime(item.get("observed_at")),
                str(item.get("observed_in_run_id", "")),
                str(item.get("source_snapshot_id", "")),
                str(item.get("proposition_version_id", "")),
            ),
        )
        enriched_versions = self._with_proposition_comparisons(versions=ordered_versions)
        grouped_by_snapshot = self._group_versions_by_snapshot(versions=enriched_versions)
        grouped_by_run = self._group_versions_by_run(versions=enriched_versions)

        return {
            "proposition_key": normalized_key,
            "scope": "aggregated_history",
            "include_runs": include_runs,
            "run_ids_scanned": sorted(run_ids_scanned),
            "observed_version_count": len(enriched_versions),
            "observed_versions": enriched_versions,
            "versions_by_run": grouped_by_run,
            "versions_by_snapshot": grouped_by_snapshot,
        }

    def divergence_history(
        self,
        finding_id: str,
        *,
        include_runs: bool = True,
    ) -> dict[str, Any]:
        normalized_finding_id = finding_id.strip()
        if not normalized_finding_id:
            raise OperationsError("finding_id must be a non-empty string.")

        run_ids_scanned: list[str] = []
        observed_versions: list[dict[str, Any]] = []
        seen_observation_ids: set[str] = set()

        if include_runs:
            entries = self._run_index()
            for entry in entries:
                run_ids_scanned.append(entry.run_id)
                assessments = self._artifact_list(
                    entry=entry, artifact_type="divergence_assessments"
                )
                propositions = self._artifact_list(entry=entry, artifact_type="propositions")
                proposition_by_id = {
                    str(item.get("id")): item
                    for item in propositions
                    if isinstance(item, dict) and str(item.get("id", ""))
                }
                for assessment in assessments:
                    assessment_finding_id = str(
                        assessment.get("finding_id")
                        or "finding-"
                        + str(assessment.get("proposition_id", ""))
                        + "-"
                        + str(assessment.get("comparator_proposition_id", ""))
                    )
                    if assessment_finding_id != normalized_finding_id:
                        continue
                    observation = self._build_divergence_observation(
                        finding_id=normalized_finding_id,
                        assessment=assessment,
                        proposition_by_id=proposition_by_id,
                        fallback_run_id=entry.run_id,
                        fallback_run_created_at=entry.run_payload.get("created_at"),
                    )
                    observation_id = self._divergence_observation_id(observation=observation)
                    if observation_id in seen_observation_ids:
                        continue
                    seen_observation_ids.add(observation_id)
                    observed_versions.append(observation)

        if not observed_versions:
            raise OperationsError(
                f"Finding id {normalized_finding_id!r} was not found in exported runs."
            )

        ordered_versions = sorted(
            observed_versions,
            key=lambda item: (
                self._safe_datetime(item.get("observed_at")),
                str(item.get("observed_in_run_id", "")),
                "::".join(item.get("source_snapshot_ids", []))
                if isinstance(item.get("source_snapshot_ids"), list)
                else "",
                str(item.get("observation_id", "")),
            ),
        )
        enriched_versions = self._with_divergence_comparisons(versions=ordered_versions)
        grouped_by_snapshot = self._group_divergence_versions_by_snapshot(
            versions=enriched_versions
        )
        grouped_by_run = self._group_divergence_versions_by_run(versions=enriched_versions)

        return {
            "finding_id": normalized_finding_id,
            "scope": "aggregated_history",
            "include_runs": include_runs,
            "run_ids_scanned": sorted(run_ids_scanned),
            "observed_version_count": len(enriched_versions),
            "observed_versions": enriched_versions,
            "versions_by_run": grouped_by_run,
            "versions_by_snapshot": grouped_by_snapshot,
        }

    def _artifact_payload(
        self, *, entry: RunIndexEntry, artifact_type: str, default: Any
    ) -> list[dict[str, Any]] | dict[str, Any]:
        artifacts = entry.manifest.get("artifacts", [])
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                if str(artifact.get("artifact_type")) != artifact_type:
                    continue
                storage_uri = artifact.get("storage_uri")
                if not isinstance(storage_uri, str):
                    break
                payload = self._read_by_storage_uri(storage_uri, default=default)
                if isinstance(payload, (list, dict)):
                    return payload
                return default

        if artifact_type == "pipeline_review_decisions":
            root_prd = self._read_json_file(
                self.export_dir / "pipeline_review_decisions.json",
                default=default,
            )
            if isinstance(root_prd, list):
                return root_prd
        if artifact_type == "source_records":
            root_sources = self._read_json_file(self.export_dir / "sources.json", default=default)
            if isinstance(root_sources, (list, dict)):
                return root_sources
        if artifact_type == "legal_scopes":
            root_ls = self._read_json_file(self.export_dir / "legal_scopes.json", default=default)
            if isinstance(root_ls, list):
                return root_ls
        if artifact_type == "proposition_scope_links":
            root_psl = self._read_json_file(
                self.export_dir / "proposition_scope_links.json",
                default=default,
            )
            if isinstance(root_psl, list):
                return root_psl
        if artifact_type == "scope_inventory":
            root_si = self._read_json_file(self.export_dir / "scope_inventory.json", default={})
            if isinstance(root_si, dict):
                return root_si
        if artifact_type == "scope_review_candidates":
            root_src = self._read_json_file(
                self.export_dir / "scope_review_candidates.json",
                default=default,
            )
            if isinstance(root_src, list):
                return root_src
        if artifact_type == "proposition_completeness_assessments":
            root_pca = self._read_json_file(
                self.export_dir / "proposition_completeness_assessments.json",
                default=default,
            )
            if isinstance(root_pca, list):
                return root_pca
        if artifact_type == "decision_explanations":
            root_dexp = self._read_json_file(
                self.export_dir / "decision_explanations.json",
                default=default,
            )
            if isinstance(root_dexp, dict):
                return root_dexp
        return default

    def _normalize_source_record_rows(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("sources", "source_records", "rows"):
                inner = payload.get(key)
                if isinstance(inner, list):
                    return [item for item in inner if isinstance(item, dict)]
        return []

    def _source_record_row_id(self, row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("source_record_id") or "").strip()

    def _root_run_matches_entry(self, entry: RunIndexEntry) -> bool:
        root_run = self._read_json_file(self.export_dir / "run.json", default={})
        return isinstance(root_run, dict) and str(root_run.get("id") or "") == entry.run_id

    def _source_records_payload_from_manifest(
        self, entry: RunIndexEntry, default: Any
    ) -> list[dict[str, Any]] | dict[str, Any]:
        artifacts = entry.manifest.get("artifacts", [])
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                if str(artifact.get("artifact_type")) != "source_records":
                    continue
                storage_uri = artifact.get("storage_uri")
                if not isinstance(storage_uri, str):
                    break
                payload = self._read_by_storage_uri(storage_uri, default=default)
                if isinstance(payload, (list, dict)):
                    return payload
                return default
        return default

    def _inventory_summary_source_records(self, entry: RunIndexEntry) -> list[dict[str, Any]]:
        inv = self._artifact_payload(entry=entry, artifact_type="source_inventory", default={})
        if not isinstance(inv, dict):
            return []
        rows = inv.get("rows")
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("source_record_id") or "").strip()
            if not sid:
                continue
            out.append(
                {
                    "id": sid,
                    "title": row.get("title"),
                    "jurisdiction": row.get("jurisdiction"),
                    "citation": row.get("citation"),
                    "instrument_id": row.get("instrument_id"),
                    "kind": row.get("instrument_type"),
                    "review_status": row.get("status"),
                    "source_url": row.get("source_url"),
                    "version_id": row.get("version_id"),
                    "content_hash": row.get("content_hash"),
                    "_summary_only": True,
                }
            )
        return out

    def _merged_source_records_for_run(self, entry: RunIndexEntry) -> list[dict[str, Any]]:
        primary_raw = self._source_records_payload_from_manifest(entry, default=[])
        primary = self._normalize_source_record_rows(primary_raw)

        mirror: list[dict[str, Any]] = []
        if self._root_run_matches_entry(entry):
            mirror_raw = self._read_json_file(self.export_dir / "sources.json", default=[])
            mirror = self._normalize_source_record_rows(mirror_raw)

        inventory_rows = self._inventory_summary_source_records(entry)

        by_id: dict[str, dict[str, Any]] = {}
        order: list[str] = []

        def touch(sid: str, row: dict[str, Any], *, overlay: bool) -> None:
            if sid not in by_id:
                order.append(sid)
                by_id[sid] = dict(row)
            elif overlay:
                merged = {**by_id[sid], **dict(row)}
                by_id[sid] = merged

        for row in mirror:
            sid = self._source_record_row_id(row)
            if sid:
                touch(sid, row, overlay=False)

        for row in primary:
            sid = self._source_record_row_id(row)
            if sid:
                touch(sid, row, overlay=True)

        have = set(by_id.keys())
        for row in inventory_rows:
            sid = self._source_record_row_id(row)
            if sid and sid not in have:
                touch(sid, row, overlay=False)
                have.add(sid)

        return [by_id[sid] for sid in order if sid in by_id]

    def _artifact_list(self, *, entry: RunIndexEntry, artifact_type: str) -> list[dict[str, Any]]:
        if artifact_type == "source_records":
            return self._merged_source_records_for_run(entry)
        payload = self._artifact_payload(entry=entry, artifact_type=artifact_type, default=[])
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _resolve_run_entry(self, run_id: str | None) -> RunIndexEntry:
        entries = self._run_index()
        if not entries:
            raise OperationsError(
                f"No exported runs found under {self.export_dir}. Export a case first."
            )
        if run_id:
            for entry in entries:
                if entry.run_id == run_id:
                    return entry
            known = ", ".join(sorted(item.run_id for item in entries))
            raise OperationsError(f"Run {run_id!r} was not found. Known runs: {known}.")

        return sorted(
            entries,
            key=lambda item: (
                str(item.run_payload.get("created_at", "")),
                item.run_id,
            ),
            reverse=True,
        )[0]

    def _snapshot_event_id(self, *, snapshot: dict[str, Any]) -> str:
        source_record_id = str(snapshot.get("source_record_id", ""))
        version_id = str(snapshot.get("version_id", ""))
        content_hash = str(snapshot.get("content_hash", ""))
        retrieved_at = str(snapshot.get("retrieved_at", ""))
        return (
            "snapshot-event::"
            + source_record_id
            + "::"
            + version_id
            + "::"
            + content_hash
            + "::"
            + retrieved_at
        )

    def _build_timeline_events(
        self,
        *,
        source_id: str,
        snapshots: list[dict[str, Any]],
        extra_by_event_id: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        ordered = sorted(
            [item for item in snapshots if isinstance(item, dict)],
            key=lambda item: (
                self._safe_datetime(item.get("retrieved_at")),
                str(item.get("as_of_date", "")),
                str(item.get("id", "")),
            ),
        )
        timeline: list[dict[str, Any]] = []
        previous: dict[str, Any] | None = None
        previous_event_id: str | None = None
        extras = extra_by_event_id or {}
        for position, snapshot in enumerate(ordered):
            event_id = self._snapshot_event_id(snapshot=snapshot)
            comparison = self._compare_snapshots(
                current=snapshot,
                previous=previous,
                previous_event_id=previous_event_id,
            )
            timeline_event = {
                "event_id": event_id,
                "position": position,
                "source_record_id": str(snapshot.get("source_record_id", source_id)),
                "snapshot_id": snapshot.get("id"),
                "version_id": snapshot.get("version_id"),
                "content_hash": snapshot.get("content_hash"),
                "retrieved_at": snapshot.get("retrieved_at"),
                "as_of_date": snapshot.get("as_of_date"),
                "provenance": snapshot.get("provenance"),
                "authoritative_locator": snapshot.get("authoritative_locator"),
                "snapshot": snapshot,
                "comparison": comparison,
            }
            if event_id in extras:
                timeline_event.update(extras[event_id])
            timeline.append(timeline_event)
            previous = snapshot
            previous_event_id = event_id
        return timeline

    def _upsert_history_event(
        self,
        *,
        event_by_id: dict[str, dict[str, Any]],
        snapshot: dict[str, Any],
        origin: dict[str, Any],
    ) -> None:
        event_id = self._snapshot_event_id(snapshot=snapshot)
        existing = event_by_id.get(event_id)
        if existing is None:
            event_by_id[event_id] = {
                "snapshot": snapshot,
                "origins": [origin],
            }
            return

        origins = existing.get("origins")
        if not isinstance(origins, list):
            origins = []
        if origin not in origins:
            origins.append(origin)
        existing["origins"] = origins

        existing_snapshot = existing.get("snapshot")
        if not isinstance(existing_snapshot, dict):
            existing["snapshot"] = snapshot
            return
        existing_text = str(existing_snapshot.get("authoritative_text", ""))
        incoming_text = str(snapshot.get("authoritative_text", ""))
        if incoming_text and not existing_text:
            existing["snapshot"] = snapshot

    def _registry_entries(self) -> list[dict[str, Any]]:
        if self.source_registry_path is None or not self.source_registry_path.exists():
            return []
        payload = self._read_json_file(self.source_registry_path, default={})
        if not isinstance(payload, dict):
            return []
        sources = payload.get("sources", [])
        if not isinstance(sources, list):
            return []
        return [item for item in sources if isinstance(item, dict)]

    def _registry_refresh_snapshot(
        self,
        *,
        source_id: str,
        history_item: dict[str, Any],
        reference_snapshot: dict[str, Any] | None,
        registry_id: str,
    ) -> dict[str, Any]:
        snapshot_id = str(history_item.get("source_snapshot_id", ""))
        content_hash = str(history_item.get("content_hash", ""))
        reference = reference_snapshot or {}
        reference_retrieved_at = str(reference.get("retrieved_at", ""))
        refreshed_at = str(history_item.get("refreshed_at", ""))
        return {
            "id": snapshot_id or str(reference.get("id", "")),
            "source_record_id": source_id,
            "version_id": str(
                history_item.get("version_id") or reference.get("version_id") or "unknown"
            ),
            "authoritative_text": str(reference.get("authoritative_text", "")),
            "authoritative_locator": str(reference.get("authoritative_locator", "document:full")),
            "provenance": str(reference.get("provenance") or "registry.refresh_history"),
            "as_of_date": reference.get("as_of_date"),
            "retrieved_at": reference_retrieved_at or refreshed_at,
            "content_hash": content_hash or str(reference.get("content_hash", "")),
            "metadata": {
                "registry_id": registry_id,
                "decision": history_item.get("decision"),
                "cache_key": history_item.get("cache_key"),
                "source": "registry.refresh_history",
            },
        }

    def _compare_snapshots(
        self,
        *,
        current: dict[str, Any],
        previous: dict[str, Any] | None,
        previous_event_id: str | None,
    ) -> dict[str, Any]:
        if previous is None:
            return {
                "has_previous": False,
                "baseline_event_id": None,
                "baseline_snapshot_id": None,
                "text_changed": False,
                "metadata_changed": False,
                "change_kind": "initial",
                "metadata_diff": [],
                "text_diff": "",
            }

        current_text = str(current.get("authoritative_text", ""))
        previous_text = str(previous.get("authoritative_text", ""))
        current_hash = str(current.get("content_hash", ""))
        previous_hash = str(previous.get("content_hash", ""))
        text_changed = (current_hash != previous_hash) or (current_text != previous_text)
        text_diff = (
            "\n".join(
                unified_diff(
                    previous_text.splitlines(),
                    current_text.splitlines(),
                    fromfile=str(previous.get("id", "previous")),
                    tofile=str(current.get("id", "current")),
                    lineterm="",
                )
            )
            if text_changed
            else ""
        )

        metadata_diff = self._metadata_diff(current=current, previous=previous)
        metadata_changed = len(metadata_diff) > 0
        if text_changed and metadata_changed:
            change_kind = "text_and_metadata"
        elif text_changed:
            change_kind = "text_only"
        elif metadata_changed:
            change_kind = "metadata_only"
        else:
            change_kind = "no_change"

        return {
            "has_previous": True,
            "baseline_event_id": previous_event_id,
            "baseline_snapshot_id": previous.get("id"),
            "text_changed": text_changed,
            "metadata_changed": metadata_changed,
            "change_kind": change_kind,
            "metadata_diff": metadata_diff,
            "text_diff": text_diff,
        }

    def _metadata_diff(
        self, *, current: dict[str, Any], previous: dict[str, Any]
    ) -> list[dict[str, Any]]:
        fields = [
            "version_id",
            "retrieved_at",
            "as_of_date",
            "provenance",
            "authoritative_locator",
            "content_hash",
        ]
        changed: list[dict[str, Any]] = []
        for field_name in fields:
            current_value = current.get(field_name)
            previous_value = previous.get(field_name)
            if current_value != previous_value:
                changed.append(
                    {
                        "field": field_name,
                        "previous": previous_value,
                        "current": current_value,
                    }
                )
        return changed

    def _safe_datetime(self, value: Any) -> datetime:
        if not isinstance(value, str) or not value.strip():
            return datetime.min
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.min

    def _build_proposition_observation(
        self,
        *,
        proposition: dict[str, Any],
        fallback_run_id: str,
        fallback_run_created_at: Any,
    ) -> dict[str, Any]:
        observed_in_run_id = str(proposition.get("observed_in_run_id") or fallback_run_id)
        observed_at = proposition.get("observed_at")
        if not isinstance(observed_at, str) or not observed_at.strip():
            observed_at = fallback_run_created_at
        if not isinstance(observed_at, str) or not observed_at.strip():
            observed_at = ""

        return {
            "proposition_id": proposition.get("id"),
            "proposition_key": proposition.get("proposition_key"),
            "proposition_version_id": proposition.get("proposition_version_id"),
            "source_record_id": proposition.get("source_record_id")
            or proposition.get("source_document_id"),
            "source_snapshot_id": proposition.get("source_snapshot_id"),
            "observed_in_run_id": observed_in_run_id,
            "observed_at": observed_at,
            "article_reference": proposition.get("article_reference"),
            "fragment_locator": proposition.get("fragment_locator"),
            "legal_subject": proposition.get("legal_subject"),
            "action": proposition.get("action"),
            "proposition_text": proposition.get("proposition_text"),
            "metadata": {
                "source_record_id": proposition.get("source_record_id")
                or proposition.get("source_document_id"),
                "source_fragment_id": proposition.get("source_fragment_id"),
                "jurisdiction": proposition.get("jurisdiction"),
            },
        }

    def _build_divergence_observation(
        self,
        *,
        finding_id: str,
        assessment: dict[str, Any],
        proposition_by_id: dict[str, dict[str, Any]],
        fallback_run_id: str,
        fallback_run_created_at: Any,
    ) -> dict[str, Any]:
        metadata = assessment.get("metadata")
        metadata_record = metadata if isinstance(metadata, dict) else {}
        proposition_id = str(assessment.get("proposition_id", ""))
        comparator_proposition_id = str(assessment.get("comparator_proposition_id", ""))
        proposition = proposition_by_id.get(proposition_id, {})
        comparator = proposition_by_id.get(comparator_proposition_id, {})

        source_record_ids = self._dedup_ordered_strings(
            [
                proposition.get("source_record_id"),
                proposition.get("source_document_id"),
                comparator.get("source_record_id"),
                comparator.get("source_document_id"),
                *(
                    assessment.get("source_record_ids", [])
                    if isinstance(assessment.get("source_record_ids"), list)
                    else []
                ),
            ]
        )

        source_snapshot_ids = self._dedup_ordered_strings(
            [
                *(
                    assessment.get("source_snapshot_ids", [])
                    if isinstance(assessment.get("source_snapshot_ids"), list)
                    else []
                ),
                proposition.get("source_snapshot_id"),
                comparator.get("source_snapshot_id"),
            ]
        )

        observed_in_run_id = str(
            assessment.get("observed_in_run_id")
            or metadata_record.get("observed_in_run_id")
            or fallback_run_id
        )
        observed_at = assessment.get("observed_at")
        if not isinstance(observed_at, str) or not observed_at.strip():
            observed_at = metadata_record.get("observed_at")
        if not isinstance(observed_at, str) or not observed_at.strip():
            observed_at = fallback_run_created_at
        if not isinstance(observed_at, str) or not observed_at.strip():
            observed_at = ""

        observation_id = str(assessment.get("id") or "")
        version_identity = self._divergence_version_identity(
            finding_id=finding_id,
            observation_id=observation_id,
            observed_in_run_id=observed_in_run_id,
            source_snapshot_ids=source_snapshot_ids,
        )

        return {
            "finding_id": finding_id,
            "observation_id": observation_id,
            "version_identity": version_identity,
            "source_record_ids": source_record_ids,
            "source_snapshot_ids": source_snapshot_ids,
            "observed_in_run_id": observed_in_run_id,
            "observed_at": observed_at,
            "divergence_type": assessment.get("divergence_type"),
            "confidence": assessment.get("confidence"),
            "review_status": assessment.get("review_status"),
            "rationale": assessment.get("rationale"),
            "operational_impact": assessment.get("operational_impact"),
            "metadata": metadata_record,
        }

    def _proposition_observation_id(self, *, observation: dict[str, Any]) -> str:
        return "::".join(
            [
                "proposition-observation",
                str(observation.get("proposition_key", "")),
                str(observation.get("proposition_version_id", "")),
                str(observation.get("source_snapshot_id", "")),
                str(observation.get("observed_in_run_id", "")),
                str(observation.get("proposition_id", "")),
            ]
        )

    def _divergence_observation_id(self, *, observation: dict[str, Any]) -> str:
        raw_source_snapshot_ids = observation.get("source_snapshot_ids")
        source_snapshot_ids = (
            [str(item) for item in raw_source_snapshot_ids]
            if isinstance(raw_source_snapshot_ids, list)
            else []
        )
        return "::".join(
            [
                "divergence-observation",
                str(observation.get("finding_id", "")),
                str(observation.get("observation_id", "")),
                str(observation.get("observed_in_run_id", "")),
                "::".join(str(item) for item in source_snapshot_ids),
            ]
        )

    def _divergence_version_identity(
        self,
        *,
        finding_id: str,
        observation_id: str,
        observed_in_run_id: str,
        source_snapshot_ids: list[str],
    ) -> str:
        return "::".join(
            [
                "divergence-version",
                finding_id,
                observation_id or "observation-unknown",
                observed_in_run_id or "run-unknown",
                "|".join(source_snapshot_ids),
            ]
        )

    def _with_proposition_comparisons(
        self, *, versions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        previous: dict[str, Any] | None = None
        for observation in versions:
            comparison = self._compare_proposition_observations(
                current=observation,
                previous=previous,
            )
            enriched.append(
                {
                    **observation,
                    "previous_version_signal": comparison.get("signal", "no_change"),
                    "previous_version_comparison": comparison,
                }
            )
            previous = observation
        return enriched

    def _with_divergence_comparisons(
        self, *, versions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        previous: dict[str, Any] | None = None
        for observation in versions:
            comparison = self._compare_divergence_observations(
                current=observation,
                previous=previous,
            )
            enriched.append(
                {
                    **observation,
                    "previous_version_signal": comparison.get("signal", "no_change"),
                    "previous_version_comparison": comparison,
                }
            )
            previous = observation
        return enriched

    def _group_versions_by_snapshot(
        self, *, versions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for version in versions:
            snapshot_id = str(version.get("source_snapshot_id") or "snapshot-unknown")
            grouped.setdefault(snapshot_id, []).append(version)
        return [
            {
                "source_snapshot_id": snapshot_id,
                "observed_version_count": len(snapshot_versions),
                "observed_versions": snapshot_versions,
            }
            for snapshot_id, snapshot_versions in sorted(grouped.items(), key=lambda item: item[0])
        ]

    def _group_versions_by_run(self, *, versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for version in versions:
            run_id = str(version.get("observed_in_run_id") or "run-unknown")
            grouped.setdefault(run_id, []).append(version)
        return [
            {
                "observed_in_run_id": run_id,
                "observed_version_count": len(run_versions),
                "observed_versions": run_versions,
            }
            for run_id, run_versions in sorted(grouped.items(), key=lambda item: item[0])
        ]

    def _group_divergence_versions_by_snapshot(
        self, *, versions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for version in versions:
            snapshot_ids = version.get("source_snapshot_ids")
            if isinstance(snapshot_ids, list) and snapshot_ids:
                for snapshot_id in snapshot_ids:
                    key = str(snapshot_id or "snapshot-unknown")
                    grouped.setdefault(key, []).append(version)
                continue
            grouped.setdefault("snapshot-unknown", []).append(version)

        return [
            {
                "source_snapshot_id": snapshot_id,
                "observed_version_count": len(snapshot_versions),
                "observed_versions": snapshot_versions,
            }
            for snapshot_id, snapshot_versions in sorted(grouped.items(), key=lambda item: item[0])
        ]

    def _group_divergence_versions_by_run(
        self, *, versions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for version in versions:
            run_id = str(version.get("observed_in_run_id") or "run-unknown")
            grouped.setdefault(run_id, []).append(version)
        return [
            {
                "observed_in_run_id": run_id,
                "observed_version_count": len(run_versions),
                "observed_versions": run_versions,
            }
            for run_id, run_versions in sorted(grouped.items(), key=lambda item: item[0])
        ]

    def _compare_proposition_observations(
        self,
        *,
        current: dict[str, Any],
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if previous is None:
            return {
                "has_previous": False,
                "baseline_proposition_version_id": None,
                "text_changed": False,
                "metadata_changed": False,
                "signal": "no_change",
                "metadata_diff": [],
            }

        current_text = str(current.get("proposition_text", ""))
        previous_text = str(previous.get("proposition_text", ""))
        text_changed = current_text != previous_text
        metadata_diff = self._proposition_metadata_diff(current=current, previous=previous)
        metadata_changed = len(metadata_diff) > 0

        if text_changed and metadata_changed:
            signal = "both"
        elif text_changed:
            signal = "text_changed"
        elif metadata_changed:
            signal = "metadata_changed"
        else:
            signal = "no_change"

        return {
            "has_previous": True,
            "baseline_proposition_version_id": previous.get("proposition_version_id"),
            "text_changed": text_changed,
            "metadata_changed": metadata_changed,
            "signal": signal,
            "metadata_diff": metadata_diff,
        }

    def _compare_divergence_observations(
        self,
        *,
        current: dict[str, Any],
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if previous is None:
            return {
                "has_previous": False,
                "baseline_observation_id": None,
                "baseline_version_identity": None,
                "signal": "initial",
                "changed_fields": [],
            }

        comparable_fields = [
            "source_record_ids",
            "source_snapshot_ids",
            "divergence_type",
            "confidence",
            "review_status",
            "rationale",
            "operational_impact",
        ]
        changed_fields: list[dict[str, Any]] = []
        for field_name in comparable_fields:
            current_value = current.get(field_name)
            previous_value = previous.get(field_name)
            if current_value == previous_value:
                continue
            changed_fields.append(
                {
                    "field": field_name,
                    "previous": previous_value,
                    "current": current_value,
                }
            )

        signal = "changed" if changed_fields else "no_change"
        return {
            "has_previous": True,
            "baseline_observation_id": previous.get("observation_id"),
            "baseline_version_identity": previous.get("version_identity"),
            "signal": signal,
            "changed_fields": changed_fields,
        }

    def _proposition_metadata_diff(
        self,
        *,
        current: dict[str, Any],
        previous: dict[str, Any],
    ) -> list[dict[str, Any]]:
        metadata_fields = [
            "source_snapshot_id",
            "observed_in_run_id",
            "article_reference",
            "fragment_locator",
            "legal_subject",
            "action",
        ]
        changed: list[dict[str, Any]] = []
        for field_name in metadata_fields:
            current_value = current.get(field_name)
            previous_value = previous.get(field_name)
            if current_value == previous_value:
                continue
            changed.append(
                {
                    "field": field_name,
                    "previous": previous_value,
                    "current": current_value,
                }
            )
        return changed

    def _dedup_ordered_strings(self, values: list[Any]) -> list[str]:
        ordered: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = value.strip()
            if not normalized or normalized in ordered:
                continue
            ordered.append(normalized)
        return ordered

    def _run_index(self) -> list[RunIndexEntry]:
        runs_dir = self.export_dir / "runs"
        if not runs_dir.exists():
            return []

        entries: list[RunIndexEntry] = []
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            manifest = self._read_json_file(run_dir / "manifest.json", default={})
            run_payload = self._read_json_file(run_dir / "run.json", default={})
            if not isinstance(manifest, dict) or not isinstance(run_payload, dict):
                continue
            run_id = str(manifest.get("run_id") or run_payload.get("id") or "")
            if not run_id:
                continue
            entries.append(
                RunIndexEntry(
                    run_id=run_id,
                    run_dir=run_dir,
                    manifest=manifest,
                    run_payload=run_payload,
                )
            )
        return entries

    def _read_by_storage_uri(self, storage_uri: str, default: Any = None) -> Any:
        return self._read_json_file(self.export_dir / storage_uri, default=default)

    def _read_json_file(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
        return payload
