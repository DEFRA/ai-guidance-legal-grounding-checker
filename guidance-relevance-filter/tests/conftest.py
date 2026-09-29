"""Shared fixtures for the guidance-relevance-filter test suite."""

import pytest


@pytest.fixture
def build_page():
    """Factory for an input page; override the body text or add meta_data fields."""
    def _build(*, body_text="Guidance on slurry storage.", **meta):
        return {
            "url": "https://example.gov.uk/slurry",
            "content_id": "abc",
            "meta_data": {"title": "Slurry storage", "body_text": body_text, **meta},
        }

    return _build
