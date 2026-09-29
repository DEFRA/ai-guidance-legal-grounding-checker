"""Proposition extraction trace linking (ADR-0018: identity vs lineage vs display)."""

import re

from law_proposition_extractor_pipeline.runner import _opaque_proposition_extraction_trace_id


def test_extraction_trace_id_is_deterministic_opaque() -> None:
    pid = "prop:aabbccddeeff0011"
    a = _opaque_proposition_extraction_trace_id(pid)
    b = _opaque_proposition_extraction_trace_id(pid)
    assert a == b
    assert re.fullmatch(r"extract-trace:[a-f0-9]{16}", a)


def test_extraction_trace_ids_differ_across_propositions() -> None:
    assert _opaque_proposition_extraction_trace_id("prop:1111111111111111") != (
        _opaque_proposition_extraction_trace_id("prop:2222222222222222")
    )
