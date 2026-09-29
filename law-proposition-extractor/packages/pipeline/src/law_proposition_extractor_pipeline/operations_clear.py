"""Dev/admin helpers to wipe local operations bundles and related state without touching pipeline semantics."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

EMPTY_SOURCE_REGISTRY_PAYLOAD: dict[str, Any] = {"version": "0.1", "sources": []}


class UnsafeExportDirError(ValueError):
    """Raised when refusing destructive clear on a suspicious export directory."""


class ClearOperationsConfirmationError(ValueError):
    """Raised when destructive clear is requested without --confirm."""


Mode = Literal["runs_only", "all"]


@dataclass(frozen=True)
class ClearOperationsOutcome:
    mode: Mode
    dry_run: bool
    export_dir: str
    deleted_paths_export: tuple[str, ...]
    preserved_registry_path: str | None
    cleared_source_cache_paths: tuple[str, ...]
    cleared_derived_cache_paths: tuple[str, ...]
    registry_reset_written: bool
    messages: tuple[str, ...] = field(default_factory=tuple)


def default_source_registry_path() -> Path:
    return Path(__import__("tempfile").gettempdir()) / "law-proposition-extractor" / "source-registry.json"


def default_source_cache_dir() -> Path:
    return Path(__import__("tempfile").gettempdir()) / "law-proposition-extractor" / "source-snapshots"


def default_derived_cache_dir() -> Path:
    return Path(__import__("tempfile").gettempdir()) / "law-proposition-extractor" / "derived-artifacts"


def _reject_unsafe_export_dir(export_dir: Path) -> None:
    resolved = export_dir.expanduser().resolve()
    anchor = resolved.anchor or "/"
    if resolved == Path(anchor) or str(resolved) in {"/"}:
        raise UnsafeExportDirError(f"Refusing destructive clear at root: {export_dir}")


def _list_recursive_paths_readable(root: Path) -> tuple[str, ...]:
    """All files/dirs under root (exclusive of root itself), deterministic order."""

    if not root.exists():
        return ()
    pairs: list[tuple[list[str], str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root.resolve())
        rel_parts = list(relative.parts)
        pairs.append((rel_parts, str(path.resolve())))
    pairs.sort(key=lambda item: (-len(item[0]), item[1]))
    return tuple(p[1] for p in pairs) + ((str(root.resolve()),) if root.exists() else ())


def _reset_registry_payload(registry_path: Path) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(EMPTY_SOURCE_REGISTRY_PAYLOAD, indent=2),
        encoding="utf-8",
    )


def wipe_export_bundle_keep_registry_elsewhere(
    export_dir: str | Path,
    *,
    source_registry_resolved_elsewhere: Path | None,
) -> list[str]:
    """
    Replace ``export_dir`` with an empty directory.

    When ``source_registry_resolved_elsewhere`` identifies a registry file under ``export_dir``,
    that file is preserved by copying it aside before the tree is removed, then restored afterward.
    """

    root = Path(export_dir)
    _reject_unsafe_export_dir(root)
    export_resolved = root.resolve()
    deleted_log: list[str] = []

    nested_registry: Path | None = None
    backup_path: Path | None = None
    if source_registry_resolved_elsewhere is not None:
        reg = source_registry_resolved_elsewhere.resolve()
        try:
            reg.relative_to(export_resolved)
            nested_registry = reg
        except ValueError:
            nested_registry = None

    if nested_registry is not None and nested_registry.exists():
        tmp_fd, tmp_name = tempfile.mkstemp(
            suffix=".law-proposition-extractor-registry-restore.json", prefix=".lpe-", dir=str(export_resolved.parent)
        )
        os.close(tmp_fd)
        backup_path = Path(tmp_name)
        shutil.copy2(nested_registry, backup_path)

    if export_resolved.exists():
        deleted_log.extend(_list_recursive_paths_readable(export_resolved))
        shutil.rmtree(export_resolved)

    export_resolved.mkdir(parents=True, exist_ok=True)

    if backup_path is not None and nested_registry is not None:
        nested_registry.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(backup_path), str(nested_registry))
        deleted_log.append(f"(restored preserved registry) {nested_registry}")

    return deleted_log


def clear_cache_directory_contents(directory: Path) -> list[str]:
    """Clear a cache directory recursively, then recreate it empty."""

    _reject_unsafe_export_dir(directory)
    resolved = directory.resolve()
    log: list[str] = []

    if not resolved.exists():
        resolved.mkdir(parents=True, exist_ok=True)
        return [str(resolved)]

    if resolved.is_file():
        resolved.unlink(missing_ok=True)
        resolved.mkdir(parents=True, exist_ok=True)
        log.append(str(resolved))
        return log

    log.extend(_list_recursive_paths_readable(resolved))
    shutil.rmtree(resolved)

    resolved.mkdir(parents=True, exist_ok=True)
    log.extend([str(resolved)])
    return log


def plan_clear_operations_runs_only(
    export_dir: str | Path,
    *,
    source_registry_path: str | Path | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(would_delete_display, preserved_display)``.

    Export bundle deletion is represented as wiping the resolved export dir (not every leaf) for
    readability; callers may list leaves separately if needed via ``_list_recursive_paths_readable``.
    """

    export = Path(export_dir).expanduser()
    resolved_export = export.resolve()
    reg = (
        Path(source_registry_path).expanduser().resolve()
        if source_registry_path
        else default_source_registry_path().resolve()
    )

    would_delete: list[str] = []
    if resolved_export.exists():
        would_delete.extend(_list_recursive_paths_readable(resolved_export))
    else:
        would_delete.append(str(resolved_export))

    preserved = (str(reg),)
    return (tuple(would_delete), preserved)


def plan_clear_operations_all(
    export_dir: str | Path,
    *,
    source_registry_path: str | Path | None = None,
    source_cache_dir: str | Path | None = None,
    derived_cache_dir: str | Path | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(would_delete_all, preserved)`` — preserved is empty for full clear."""

    export = Path(export_dir).expanduser()
    reg = Path(source_registry_path).expanduser() if source_registry_path else default_source_registry_path()
    sc = Path(source_cache_dir).expanduser() if source_cache_dir else default_source_cache_dir()
    dd = Path(derived_cache_dir).expanduser() if derived_cache_dir else default_derived_cache_dir()

    paths: list[str] = []

    resolved_export = export.resolve()
    if resolved_export.exists():
        paths.extend(_list_recursive_paths_readable(resolved_export))
    else:
        paths.append(str(resolved_export))

    paths.append(str(reg.resolve()) + " (reset to empty registry JSON)")
    paths.append(str(sc.resolve()) + " (clear cache directory contents)")
    paths.append(str(dd.resolve()) + " (clear cache directory contents)")

    return (tuple(paths), ())


def execute_clear_operations_runs_only(
    *,
    export_dir: str | Path,
    source_registry_path: str | Path | None = None,
    dry_run: bool = False,
    confirm: bool = False,
) -> ClearOperationsOutcome:
    reg = Path(source_registry_path).expanduser() if source_registry_path else default_source_registry_path()
    resolved_reg = reg.resolve()

    would_delete, _preserved = plan_clear_operations_runs_only(export_dir, source_registry_path=str(reg))

    if dry_run:
        return ClearOperationsOutcome(
            mode="runs_only",
            dry_run=True,
            export_dir=str(Path(export_dir).resolve()),
            deleted_paths_export=would_delete,
            preserved_registry_path=str(resolved_reg),
            cleared_source_cache_paths=(),
            cleared_derived_cache_paths=(),
            registry_reset_written=False,
            messages=("Dry run: no files deleted.",),
        )

    if not confirm:
        raise ClearOperationsConfirmationError(
            "Destructive clear requires --confirm (or use --dry-run to preview)."
        )

    deleted = wipe_export_bundle_keep_registry_elsewhere(export_dir, source_registry_resolved_elsewhere=resolved_reg)

    return ClearOperationsOutcome(
        mode="runs_only",
        dry_run=False,
        export_dir=str(Path(export_dir).resolve()),
        deleted_paths_export=tuple(deleted) if deleted else would_delete,
        preserved_registry_path=str(resolved_reg),
        cleared_source_cache_paths=(),
        cleared_derived_cache_paths=(),
        registry_reset_written=False,
        messages=("Cleared operations export directory; source registry file preserved.",),
    )


def execute_clear_operations_all(
    *,
    export_dir: str | Path,
    source_registry_path: str | Path | None = None,
    source_cache_dir: str | Path | None = None,
    derived_cache_dir: str | Path | None = None,
    dry_run: bool = False,
    confirm: bool = False,
) -> ClearOperationsOutcome:
    reg = Path(source_registry_path).expanduser() if source_registry_path else default_source_registry_path()
    sc = Path(source_cache_dir).expanduser() if source_cache_dir else default_source_cache_dir()
    dd = Path(derived_cache_dir).expanduser() if derived_cache_dir else default_derived_cache_dir()

    would_delete_all, _ignored = plan_clear_operations_all(
        export_dir,
        source_registry_path=str(reg),
        source_cache_dir=str(sc),
        derived_cache_dir=str(dd),
    )

    resolved_reg = reg.resolve()

    if dry_run:
        return ClearOperationsOutcome(
            mode="all",
            dry_run=True,
            export_dir=str(Path(export_dir).resolve()),
            deleted_paths_export=would_delete_all,
            preserved_registry_path=None,
            cleared_source_cache_paths=(str(sc.resolve()),),
            cleared_derived_cache_paths=(str(dd.resolve()),),
            registry_reset_written=False,
            messages=(
                "Dry run: export bundle, caches, and registry reset not performed.",
                f"Would reset registry file: {resolved_reg}",
            ),
        )

    if not confirm:
        raise ClearOperationsConfirmationError(
            "Destructive clear requires --confirm (or use --dry-run to preview)."
        )

    wipe_export_bundle_keep_registry_elsewhere(
        export_dir,
        source_registry_resolved_elsewhere=None,
    )
    _reset_registry_payload(resolved_reg)
    clear_source = clear_cache_directory_contents(sc)
    clear_derived = clear_cache_directory_contents(dd)

    return ClearOperationsOutcome(
        mode="all",
        dry_run=False,
        export_dir=str(Path(export_dir).resolve()),
        deleted_paths_export=tuple(would_delete_all),
        preserved_registry_path=None,
        cleared_source_cache_paths=tuple(sorted(set(clear_source))),
        cleared_derived_cache_paths=tuple(sorted(set(clear_derived))),
        registry_reset_written=True,
        messages=(
            "Cleared export bundle.",
            "Reset source registry JSON to empty.",
            f"Cleared source snapshot cache at {sc.resolve()}.",
            f"Cleared derived cache at {dd.resolve()}.",
        ),
    )


def format_clear_report(outcome: ClearOperationsOutcome) -> str:
    """Plain-text listing for CLI and logs."""

    lines = [
        f"mode={outcome.mode} dry_run={outcome.dry_run}",
        f"export_dir={outcome.export_dir}",
        "",
        "Deletion / action targets:",
        *[f"  - {path}" for path in outcome.deleted_paths_export],
    ]
    if outcome.preserved_registry_path:
        lines.extend(["", f"Preserves registry file: {outcome.preserved_registry_path}"])
    if outcome.cleared_source_cache_paths:
        lines.extend(["", "Source cache clears:", *[f"  - {path}" for path in outcome.cleared_source_cache_paths]])
    if outcome.cleared_derived_cache_paths:
        lines.extend(["", "Derived cache clears:", *[f"  - {path}" for path in outcome.cleared_derived_cache_paths]])
    lines.extend(["", f"registry_reset_written={outcome.registry_reset_written}"])
    lines.extend(["", *[f"notice: {m}" for m in outcome.messages]])
    return "\n".join(lines)