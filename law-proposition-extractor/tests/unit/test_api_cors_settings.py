"""API CORS allowlist configuration (dev/local; production sets explicit origins via env)."""

import pytest
from law_proposition_extractor_api.settings import ApiSettings

_EXPECTED_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]


def test_cors_allowed_origins_defaults_match_local_next_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    s = ApiSettings()
    assert s.cors_allowed_origins == _EXPECTED_DEFAULT_ORIGINS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "http://localhost:3002 , http://127.0.0.1:3002",
            ["http://localhost:3002", "http://127.0.0.1:3002"],
        ),
        (
            "https://app.example.com",
            ["https://app.example.com"],
        ),
    ],
)
def test_cors_allowed_origins_from_env_comma_separated(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", raw)
    assert ApiSettings().cors_allowed_origins == expected


def test_cors_allowed_origins_empty_env_string_falls_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "  ,  ")
    assert ApiSettings().cors_allowed_origins == _EXPECTED_DEFAULT_ORIGINS


def test_cors_allowed_origins_blank_env_string_falls_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")
    assert ApiSettings().cors_allowed_origins == _EXPECTED_DEFAULT_ORIGINS
