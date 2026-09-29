import re
from pathlib import Path

from fastapi.testclient import TestClient
from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle


def test_api_operations_endpoints_read_exported_artifacts(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    source_id = str(bundle["source_records"][0]["id"])

    previous_export_dir = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)

        runs_response = client.get("/ops/runs")
        assert runs_response.status_code == 200
        assert runs_response.json()["runs"][0]["run_id"] == run_id

        run_response = client.get(f"/ops/runs/{run_id}")
        assert run_response.status_code == 200
        assert run_response.json()["run"]["id"] == run_id

        trace_response = client.get(f"/ops/runs/{run_id}/traces")
        assert trace_response.status_code == 200
        assert trace_response.json()["trace_count"] >= 7

        decisions_response = client.get(f"/ops/runs/{run_id}/review-decisions")
        assert decisions_response.status_code == 200
        assert decisions_response.json()["review_decisions"]

        pipeline_prd = client.get("/ops/pipeline-review-decisions", params={"run_id": run_id})
        assert pipeline_prd.status_code == 200
        assert pipeline_prd.json()["count"] == 0
        assert pipeline_prd.json()["pipeline_review_decisions"] == []

        sources_response = client.get("/ops/sources", params={"run_id": run_id})
        assert sources_response.status_code == 200
        assert any(item["id"] == source_id for item in sources_response.json()["source_records"])
        source_target_links_response = client.get(
            "/ops/source-target-links",
            params={"run_id": run_id},
        )
        assert source_target_links_response.status_code == 200
        assert source_target_links_response.json()["source_target_links"]
        source_fetch_attempts_response = client.get(
            "/ops/source-fetch-attempts",
            params={"run_id": run_id, "source_record_id": source_id},
        )
        assert source_fetch_attempts_response.status_code == 200
        assert source_fetch_attempts_response.json()["source_fetch_attempts"]
        source_fragments_response = client.get(
            "/ops/source-fragments",
            params={"run_id": run_id, "source_record_id": source_id},
        )
        assert source_fragments_response.status_code == 200
        assert source_fragments_response.json()["source_fragments"]
        first_snapshot_id = source_fragments_response.json()["source_fragments"][0][
            "source_snapshot_id"
        ]
        source_parse_traces_response = client.get(
            "/ops/source-parse-traces",
            params={"run_id": run_id, "source_snapshot_id": first_snapshot_id},
        )
        assert source_parse_traces_response.status_code == 200
        assert source_parse_traces_response.json()["source_parse_traces"]

        propositions_response = client.get("/ops/propositions", params={"run_id": run_id})
        assert propositions_response.status_code == 200
        propositions_payload = propositions_response.json()
        assert propositions_payload["propositions"]

        legal_scopes_payload = client.get("/ops/legal-scopes", params={"run_id": run_id}).json()
        assert legal_scopes_payload["count"] >= 10
        link_payload = client.get(
            "/ops/proposition-scope-links",
            params={"run_id": run_id},
        ).json()
        assert isinstance(link_payload["proposition_scope_links"], list)
        proposition_key = propositions_payload["propositions"][0]["proposition_key"]
        first_prop_id = propositions_payload["propositions"][0]["id"]
        pex_response = client.get(
            "/ops/proposition-extraction-traces",
            params={"run_id": run_id, "proposition_id": first_prop_id},
        )
        assert pex_response.status_code == 200
        pex_payload = pex_response.json()
        assert pex_payload["proposition_extraction_traces"]
        pca_all = client.get("/ops/proposition-completeness-assessments", params={"run_id": run_id})
        assert pca_all.status_code == 200
        pca_payload = pca_all.json()
        assert len(pca_payload["proposition_completeness_assessments"]) == len(
            propositions_payload["propositions"]
        )
        first_pex = pex_payload["proposition_extraction_traces"][0]
        assert first_pex["proposition_id"] == first_prop_id
        assert re.fullmatch(r"extract-trace:[a-f0-9]{16}", str(first_pex["id"]))
        assert first_pex.get("proposition_key") == proposition_key

        pipeline_append = client.post(
            f"/ops/runs/{run_id}/pipeline-review-decisions",
            json={
                "artifact_type": "proposition",
                "artifact_id": first_prop_id,
                "decision": "needs_review",
                "reviewer": "pytest",
                "reason": "",
            },
        )
        assert pipeline_append.status_code == 200
        assert pipeline_append.json()["pipeline_review_decision"]["decision"] == "needs_review"
        refreshed_prd = client.get(
            "/ops/pipeline-review-decisions",
            params={
                "run_id": run_id,
                "artifact_type": "proposition",
                "artifact_id": first_prop_id,
            },
        )
        assert refreshed_prd.status_code == 200
        assert refreshed_prd.json()["count"] >= 1

        frag_id = propositions_payload["propositions"][0].get("source_fragment_id")
        if frag_id:
            pex_frag = client.get(
                "/ops/proposition-extraction-traces",
                params={"run_id": run_id, "source_fragment_id": frag_id},
            )
            assert pex_frag.status_code == 200
            assert all(
                item.get("source_fragment_id") == frag_id
                for item in pex_frag.json()["proposition_extraction_traces"]
            )

        source_response = client.get(f"/ops/sources/{source_id}", params={"run_id": run_id})
        assert source_response.status_code == 200
        assert source_response.json()["source_record"]["id"] == source_id

        snapshots_response = client.get(
            f"/ops/sources/{source_id}/snapshots",
            params={"run_id": run_id},
        )
        assert snapshots_response.status_code == 200
        assert snapshots_response.json()["source_snapshots"]

        all_snapshots_response = client.get("/ops/source-snapshots", params={"run_id": run_id})
        assert all_snapshots_response.status_code == 200
        all_snapshots = all_snapshots_response.json()["source_snapshots"]
        assert all_snapshots
        snapshot_id = str(all_snapshots[0]["id"])
        assert "authoritative_text" not in all_snapshots[0]
        assert all_snapshots[0]["has_authoritative_text"] is True

        content_response = client.get(
            f"/ops/source-snapshots/{snapshot_id}/content",
            params={"run_id": run_id},
        )
        assert content_response.status_code == 200
        content_payload = content_response.json()
        assert content_payload["available"] is True
        assert content_payload["snapshot_id"] == snapshot_id
        assert isinstance(content_payload["content"], str)
        assert content_payload["content"].strip()

        missing_content = client.get(
            "/ops/source-snapshots/snap-does-not-exist/content",
            params={"run_id": run_id},
        )
        assert missing_content.status_code == 404

        path_injection = client.get(
            "/ops/source-snapshots/../../etc/passwd/content",
            params={"run_id": run_id},
        )
        assert path_injection.status_code in {404, 422}

        timeline_response = client.get(
            f"/ops/sources/{source_id}/timeline",
            params={"run_id": run_id},
        )
        assert timeline_response.status_code == 200
        timeline_payload = timeline_response.json()
        assert timeline_payload["source_id"] == source_id
        assert timeline_payload["timepoint_count"] >= 1
        assert timeline_payload["timepoints"][0]["event_id"].startswith("snapshot-event::")

        history_response = client.get(f"/ops/sources/{source_id}/history")
        assert history_response.status_code == 200
        history_payload = history_response.json()
        assert history_payload["source_id"] == source_id
        assert history_payload["scope"] == "aggregated_history"
        assert history_payload["timepoint_count"] >= 1

        proposition_history_response = client.get(
            f"/ops/propositions/{proposition_key}/history",
        )
        assert proposition_history_response.status_code == 200
        proposition_history_payload = proposition_history_response.json()
        assert proposition_history_payload["proposition_key"] == proposition_key
        assert proposition_history_payload["observed_version_count"] >= 1
        observed = proposition_history_payload["observed_versions"][0]
        assert observed["proposition_version_id"]
        assert observed["source_record_id"] == source_id
        assert observed["previous_version_signal"] in {
            "text_changed",
            "metadata_changed",
            "both",
            "no_change",
        }
        assert proposition_history_payload["versions_by_run"]
        assert proposition_history_payload["versions_by_snapshot"]

        quality_response = client.get("/ops/run-quality-summary", params={"run_id": run_id})
        assert quality_response.status_code == 200
        quality_payload = quality_response.json()
        assert quality_payload["run_id"] == run_id
        assert quality_payload["run_quality_summary"]["run_id"] == run_id
        assert quality_payload["run_quality_summary"]["status"] in {
            "pass",
            "pass_with_warnings",
            "fail",
        }

        divergence_response = client.get("/ops/divergence-assessments", params={"run_id": run_id})
        assert divergence_response.status_code == 200
        divergence_payload = divergence_response.json()
        assert divergence_payload["divergence_assessments"]
        first_assessment = divergence_payload["divergence_assessments"][0]
        finding_id = str(
            first_assessment.get("finding_id")
            or "finding-"
            + str(first_assessment.get("proposition_id", ""))
            + "-"
            + str(first_assessment.get("comparator_proposition_id", ""))
        )

        divergence_history_response = client.get(
            f"/ops/divergence-findings/{finding_id}/history",
        )
        assert divergence_history_response.status_code == 200
        divergence_history_payload = divergence_history_response.json()
        assert divergence_history_payload["finding_id"] == finding_id
        assert divergence_history_payload["observed_version_count"] >= 1
        divergence_observed = divergence_history_payload["observed_versions"][0]
        assert divergence_observed["observation_id"]
        assert divergence_observed["version_identity"]
        assert isinstance(divergence_observed["source_record_ids"], list)
        assert isinstance(divergence_observed["source_snapshot_ids"], list)
        assert divergence_observed["previous_version_signal"] in {"initial", "changed", "no_change"}
        assert divergence_history_payload["versions_by_run"]
        assert divergence_history_payload["versions_by_snapshot"]

        fragments_response = client.get(
            f"/ops/sources/{source_id}/fragments",
            params={"run_id": run_id},
        )
        assert fragments_response.status_code == 200
        assert fragments_response.json()["source_fragments"]
    finally:
        settings.operations_export_dir = previous_export_dir
