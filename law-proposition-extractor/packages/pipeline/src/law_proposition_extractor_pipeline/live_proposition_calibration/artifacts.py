"""Artifact I/O and offline integrity checks for live calibration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .paths import (
    CALIBRATION_CASES,
    REPETITIONS,
    call_artifact_name,
    calls_dir,
    run_dir,
)
from .recording_client import assert_no_forbidden_fields

_ABS_PATH_RE = re.compile(
    r"(?:/Users/[^\s\"']+|/(?:home|private/var)/[^\s\"']+|[A-Za-z]:\\\\(?:Users|home)[^\s\"']*)"
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_calibration_result(run_id: str, *, root: Path | None = None) -> dict[str, Any]:
    path = run_dir(run_id, root=root) / "calibration_result.json"
    return read_json(path)


def load_manifest(run_id: str, *, root: Path | None = None) -> dict[str, Any]:
    return read_json(run_dir(run_id, root=root) / "calibration_manifest.json")


def load_call_artifact(
    run_id: str, case_id: str, repetition: int, *, root: Path | None = None
) -> dict[str, Any]:
    path = calls_dir(run_id, root=root) / call_artifact_name(case_id, repetition)
    return read_json(path)


def normalize_volatile(payload: Any) -> Any:
    """Drop volatile timestamps/latencies for deterministic comparisons."""
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {
                "started_at",
                "ended_at",
                "latency_seconds",
                "runtime_seconds",
                "calibration_timestamp",
                "provider_request_id",
            }:
                continue
            out[key] = normalize_volatile(value)
        return out
    if isinstance(payload, list):
        return [normalize_volatile(x) for x in payload]
    return payload


def validate_calibration_dir(base: Path, *, expect_complete: bool = True) -> list[str]:
    """Offline integrity checks for a saved calibration run directory."""
    errors: list[str] = []
    if not base.is_dir():
        return [f"missing run directory: {base.as_posix()}"]

    for name in (
        "calibration_manifest.json",
        "calibration_result.json",
        "calibration_report.md",
    ):
        if not (base / name).is_file():
            errors.append(f"missing {name}")

    if not (base / "calls").is_dir():
        errors.append("missing calls/")
        return errors

    try:
        manifest = read_json(base / "calibration_manifest.json")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"manifest unreadable: {exc}")
        return errors

    required_manifest = {
        "calibration_run_id",
        "prompt_version",
        "model",
        "cases",
        "repetitions",
    }
    missing = required_manifest - set(manifest)
    if missing:
        errors.append(f"manifest missing keys: {sorted(missing)}")

    run_id = str(manifest.get("calibration_run_id") or base.name)

    if expect_complete:
        expected_calls = [
            call_artifact_name(case_id, rep)
            for case_id in CALIBRATION_CASES
            for rep in REPETITIONS
        ]
        for name in expected_calls:
            path = base / "calls" / name
            if not path.is_file():
                errors.append(f"missing call artifact: {name}")
                continue
            try:
                call = read_json(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: unreadable ({exc})")
                continue
            for key in (
                "calibration_run_id",
                "case_id",
                "repetition",
                "prompt_version",
                "model_alias",
                "raw_structured_response",
                "final_propositions",
                "benchmark_result",
            ):
                if key not in call:
                    errors.append(f"{name}: missing {key}")
            if not call.get("raw_structured_response") and call.get("raw_response_status") == "ok":
                errors.append(f"{name}: raw response empty while status ok")
            forbidden = assert_no_forbidden_fields(call)
            errors.extend(f"{name}: {e}" for e in forbidden)
            text = json.dumps(call)
            if _ABS_PATH_RE.search(text):
                errors.append(f"{name}: absolute local path leak")
            for bad in ("sk-ant-", "sk-proj-", "chain_of_thought", "Authorization"):
                if bad in text:
                    errors.append(f"{name}: forbidden content marker {bad}")

    try:
        result = read_json(base / "calibration_result.json")
        forbidden = assert_no_forbidden_fields(result)
        errors.extend(f"calibration_result: {e}" for e in forbidden)
        if result.get("calibration_run_id") != run_id:
            errors.append("run id mismatch between directory and payloads")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"calibration_result unreadable: {exc}")

    report = base / "calibration_report.md"
    if report.is_file():
        body = report.read_text(encoding="utf-8")
        if _ABS_PATH_RE.search(body):
            errors.append("report contains absolute local path")
        for bad in ("sk-ant-", "chain_of_thought", "Authorization: Bearer"):
            if bad in body:
                errors.append(f"report contains forbidden marker {bad}")

    return errors


def validate_calibration_artifacts(
    run_id: str, *, root: Path | None = None, expect_complete: bool = True
) -> list[str]:
    """Offline integrity checks for a saved calibration run under calibration/."""
    return validate_calibration_dir(
        run_dir(run_id, root=root), expect_complete=expect_complete
    )
