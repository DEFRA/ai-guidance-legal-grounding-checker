from guidance_relevance_web.urls import normalize_govuk_url, require_govuk_url


def test_normalizes_govuk_urls():
    assert normalize_govuk_url("https://www.gov.uk/guidance/foo/") == "https://www.gov.uk/guidance/foo"
    assert normalize_govuk_url("https://gov.uk/guidance/foo") == "https://www.gov.uk/guidance/foo"


def test_rejects_non_govuk():
    assert normalize_govuk_url("https://example.com/guidance/foo") is None
    assert normalize_govuk_url("/guidance/foo") is None


def test_require_raises():
    try:
        require_govuk_url("https://example.com/x")
    except ValueError as e:
        assert "gov.uk" in str(e)
    else:
        raise AssertionError("expected ValueError")
