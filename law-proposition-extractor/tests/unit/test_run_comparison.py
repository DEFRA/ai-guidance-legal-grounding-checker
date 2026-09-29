from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from law_proposition_extractor_pipeline.cli import app
from law_proposition_extractor_pipeline.run_comparison import compare_export_dirs, write_comparison_summary


def _write_export(root: Path, *, run_id: str, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "run.json").write_text(
        json.dumps({"id": run_id, "workflow_mode": "demo"}), encoding="utf-8"
    )
    defaults: dict[str, Any] = {
        "sources.json": payload.get("sources", []),
        "source_snapshots.json": payload.get("source_snapshots", []),
        "source_fragments.json": payload.get("source_fragments", []),
        "source_parse_traces.json": [],
        "source_fetch_metadata.json": [],
        "source_fetch_attempts.json": [],
        "source_target_links.json": [],
        "source_inventory.json": {},
        "source_categorisation_rationales.json": [],
        "propositions.json": payload.get("propositions", []),
        "proposition_extraction_traces.json": payload.get("proposition_extraction_traces", []),
        "divergence_observations.json": payload.get("divergence_observations", []),
        "divergence_assessments.json": payload.get("divergence_assessments", []),
        "divergence_findings.json": payload.get("divergence_findings", []),
        "run_artifacts.json": payload.get("run_artifacts", []),
    }
    for name, data in defaults.items():
        (root / name).write_text(json.dumps(data), encoding="utf-8")


def _minimal_source(sid: str) -> dict[str, Any]:
    return {
        "id": sid,
        "title": "T",
        "jurisdiction": "EU",
        "citation": "C",
        "kind": "regulation",
        "metadata": {},
    }


def _minimal_snapshot(sid: str, rec_id: str) -> dict[str, Any]:
    return {
        "id": sid,
        "source_record_id": rec_id,
        "version_id": "v1",
        "authoritative_text": "x",
        "provenance": "test",
        "retrieved_at": "2026-04-01T00:00:00Z",
        "content_hash": "h1",
    }


def _minimal_fragment(fid: str, rec_id: str, snap_id: str) -> dict[str, Any]:
    return {
        "id": fid,
        "source_record_id": rec_id,
        "source_snapshot_id": snap_id,
        "locator": "L",
        "fragment_text": "ft",
        "fragment_hash": "fh",
    }


def _minimal_prop(
    *,
    pid: str,
    pkey: str,
    text: str,
    src: str,
    frag: str,
    label: str = "",
    slug: str = "",
) -> dict[str, Any]:
    return {
        "id": pid,
        "proposition_key": pkey,
        "topic_id": "t1",
        "source_record_id": src,
        "source_snapshot_id": "snap-1",
        "source_fragment_id": frag,
        "jurisdiction": "EU",
        "proposition_text": text,
        "label": label,
        "slug": slug,
        "legal_subject": "ls",
        "action": "act",
    }


def test_compare_unchanged_bundles(tmp_path: Path) -> None:
    pl = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [_minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1")],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            }
        ],
    }
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_export(b, run_id="run-b", payload=pl)
    _write_export(c, run_id="run-c", payload=pl)
    out = compare_export_dirs(b, c)
    assert out["status"] == "unchanged"
    assert out["proposition_changes"]["added_count"] == 0
    assert out["proposition_changes"]["removed_count"] == 0
    assert out["proposition_changes"]["changed_count"] == 0


def test_compare_added_proposition(tmp_path: Path) -> None:
    base_pl = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [_minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1")],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            }
        ],
    }
    cand_pl = dict(base_pl)
    cand_pl["propositions"] = list(base_pl["propositions"]) + [
        _minimal_prop(pid="p2", pkey="pk-b", text="world", src="s1", frag="f1")
    ]
    cand_pl["proposition_extraction_traces"] = list(base_pl["proposition_extraction_traces"]) + [
        {
            "id": "t2",
            "proposition_id": "p2",
            "proposition_key": "pk-b",
            "source_record_id": "s1",
            "extraction_method": "heuristic",
            "extractor_name": "x",
            "extractor_version": "1",
            "status": "success",
            "confidence": "high",
            "reason": "r",
        }
    ]
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_export(b, run_id="run-b", payload=base_pl)
    _write_export(c, run_id="run-c", payload=cand_pl)
    out = compare_export_dirs(b, c)
    assert out["status"] == "changed"
    assert out["proposition_changes"]["added_count"] == 1
    assert "pk-b" in out["proposition_changes"]["added_ids"]


def test_compare_changed_proposition_text(tmp_path: Path) -> None:
    base_pl = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [_minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1")],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            }
        ],
    }
    cand_pl = dict(base_pl)
    cand_pl["propositions"] = [
        _minimal_prop(pid="p1-other-id", pkey="pk-a", text="goodbye", src="s1", frag="f1")
    ]
    cand_pl["proposition_extraction_traces"] = [
        {
            **base_pl["proposition_extraction_traces"][0],
            "proposition_id": "p1-other-id",
        }
    ]
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_export(b, run_id="run-b", payload=base_pl)
    _write_export(c, run_id="run-c", payload=cand_pl)
    out = compare_export_dirs(b, c)
    assert out["status"] == "changed"
    assert out["proposition_changes"]["changed_count"] == 1
    assert "pk-a" in out["proposition_changes"]["changed_ids"]


def test_compare_proposition_match_by_key_not_label(tmp_path: Path) -> None:
    base_pl = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [
            _minimal_prop(
                pid="p1", pkey="pk-a", text="same", src="s1", frag="f1", label="L1", slug="s1"
            )
        ],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            }
        ],
    }
    cand_pl = dict(base_pl)
    cand_pl["propositions"] = [
        _minimal_prop(
            pid="p9", pkey="pk-a", text="same", src="s1", frag="f1", label="L2", slug="s2"
        )
    ]
    cand_pl["proposition_extraction_traces"] = [
        {**base_pl["proposition_extraction_traces"][0], "proposition_id": "p9"}
    ]
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_export(b, run_id="run-b", payload=base_pl)
    _write_export(c, run_id="run-c", payload=cand_pl)
    out = compare_export_dirs(b, c)
    assert out["proposition_changes"]["added_count"] == 0
    assert out["proposition_changes"]["removed_count"] == 0
    assert out["status"] == "unchanged"


def test_regression_worse_quality_and_more_lint_errors(tmp_path: Path) -> None:
    good = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [
            _minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1"),
            _minimal_prop(pid="p2", pkey="pk-b", text="other", src="s1", frag="f1"),
        ],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            },
            {
                "id": "t2",
                "proposition_id": "p2",
                "proposition_key": "pk-b",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            },
        ],
        "divergence_observations": [],
    }
    bad = dict(good)
    bad["propositions"] = [
        {
            **_minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1"),
            "source_snapshot_id": "",
        },
        _minimal_prop(pid="p2", pkey="pk-b", text="other", src="s1", frag="f1"),
    ]
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_export(b, run_id="run-b", payload=good)
    _write_export(c, run_id="run-c", payload=bad)
    out = compare_export_dirs(b, c)
    assert out["status"] == "regression"
    assert out["quality_changes"]["changed_count"] == 1


def test_regression_mystery_proposition_drop(tmp_path: Path) -> None:
    base_pl = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [
            _minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1"),
            _minimal_prop(pid="p2", pkey="pk-b", text="keep", src="s1", frag="f1"),
        ],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            },
            {
                "id": "t2",
                "proposition_id": "p2",
                "proposition_key": "pk-b",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            },
        ],
    }
    cand_pl = dict(base_pl)
    cand_pl["propositions"] = [_minimal_prop(pid="p2", pkey="pk-b", text="keep", src="s1", frag="f1")]
    cand_pl["proposition_extraction_traces"] = [base_pl["proposition_extraction_traces"][1]]
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_export(b, run_id="run-b", payload=base_pl)
    _write_export(c, run_id="run-c", payload=cand_pl)
    out = compare_export_dirs(b, c)
    assert out["status"] == "regression"
    assert "pk-a" in (out.get("metrics") or {}).get("unexplained_proposition_removals", [])


def test_explained_proposition_drop_when_source_removed(tmp_path: Path) -> None:
    base_pl = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [_minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1")],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            }
        ],
    }
    cand_pl = {
        "sources": [],
        "source_snapshots": [],
        "source_fragments": [],
        "propositions": [],
        "proposition_extraction_traces": [],
    }
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_export(b, run_id="run-b", payload=base_pl)
    _write_export(c, run_id="run-c", payload=cand_pl)
    out = compare_export_dirs(b, c)
    assert out["status"] != "regression" or out["warnings"] == []


def test_cli_compare_runs_exit_codes(tmp_path: Path) -> None:
    pl = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [_minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1")],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            }
        ],
    }
    b = tmp_path / "ok-b"
    c = tmp_path / "ok-c"
    _write_export(b, run_id="run-b", payload=pl)
    _write_export(c, run_id="run-c", payload=pl)
    runner = CliRunner()
    r0 = runner.invoke(
        app,
        [
            "compare-runs",
            "--baseline-export-dir",
            str(b),
            "--candidate-export-dir",
            str(c),
        ],
    )
    assert r0.exit_code == 0

    bad = dict(pl)
    bad["propositions"] = [
        {**_minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1"), "source_snapshot_id": ""},
    ]
    c_bad = tmp_path / "bad-c"
    _write_export(c_bad, run_id="run-c", payload=bad)
    r1 = runner.invoke(
        app,
        [
            "compare-runs",
            "--baseline-export-dir",
            str(b),
            "--candidate-export-dir",
            str(c_bad),
        ],
    )
    assert r1.exit_code == 1

    r2 = runner.invoke(
        app,
        [
            "compare-runs",
            "--baseline-export-dir",
            str(tmp_path / "nope"),
            "--candidate-export-dir",
            str(c),
        ],
    )
    assert r2.exit_code == 2


def test_write_comparison_summary(tmp_path: Path) -> None:
    pl = {
        "sources": [_minimal_source("s1")],
        "source_snapshots": [_minimal_snapshot("snap-1", "s1")],
        "source_fragments": [_minimal_fragment("f1", "s1", "snap-1")],
        "propositions": [_minimal_prop(pid="p1", pkey="pk-a", text="hello", src="s1", frag="f1")],
        "proposition_extraction_traces": [
            {
                "id": "t1",
                "proposition_id": "p1",
                "proposition_key": "pk-a",
                "source_record_id": "s1",
                "extraction_method": "heuristic",
                "extractor_name": "x",
                "extractor_version": "1",
                "status": "success",
                "confidence": "high",
                "reason": "r",
            }
        ],
    }
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_export(b, run_id="run-b", payload=pl)
    _write_export(c, run_id="run-c", payload=pl)
    summary = compare_export_dirs(b, c)
    out_path = tmp_path / "cmp.json"
    write_comparison_summary(out_path, summary)
    assert out_path.exists()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["status"] == "unchanged"
