from pathlib import Path

import pytest


@pytest.fixture
def examples_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
