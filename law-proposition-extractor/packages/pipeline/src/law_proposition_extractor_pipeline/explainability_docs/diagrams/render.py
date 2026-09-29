"""Deterministic D2 rendering for explainability diagrams."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .paths import D2_RENDER_ARGS


class D2RenderError(RuntimeError):
    """Raised when the D2 CLI is missing or rendering fails."""


def find_d2_binary() -> str:
    binary = shutil.which("d2")
    if not binary:
        raise D2RenderError(
            "d2 binary not found on PATH. Install with `brew install d2` "
            "(see docs/process/asset-generation.md)."
        )
    return binary


def render_d2_to_svg(source: Path, output: Path, *, d2_binary: str | None = None) -> None:
    """Render ``source`` to ``output`` with fixed layout/theme/pad/scale flags."""
    binary = d2_binary or find_d2_binary()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Isolate from caller env that could change layout (watch/theme overrides).
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C"),
    }
    cmd = [binary, *D2_RENDER_ARGS, str(source), str(output)]
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise D2RenderError(f"d2 timed out rendering {source.name}") from exc
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise D2RenderError(f"d2 failed for {source.name}: {stderr}")


def assert_svg_safe(svg_text: str, *, label: str) -> None:
    if "file://" in svg_text:
        raise RuntimeError(f"{label} contains a file:// reference.")
    for token in ("/Users/", "/home/", "/private/var/", "C:\\", "file:"):
        if token in svg_text:
            raise RuntimeError(f"{label} embeds a local filesystem path ({token}).")
