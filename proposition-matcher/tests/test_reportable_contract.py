"""Pin REPORTABLE_RELATIONSHIPS so Audit Assembler's mirrored set cannot drift silently."""

from proposition_matcher.matching.match_summary import (
    REPORTABLE_RELATIONSHIPS,
    is_reportable_relationship,
)

# Keep identical to audit_assembler.match_summary.REPORTABLE_RELATIONSHIPS.
EXPECTED_REPORTABLE_RELATIONSHIPS = frozenset({
    "GROUNDED",
    "GUIDANCE_BROADER",
    "GUIDANCE_INCOMPLETE",
    "CONFLICTS",
    "GUIDANCE_MISSING",
})


def test_reportable_relationships_match_documented_contract():
    assert REPORTABLE_RELATIONSHIPS == EXPECTED_REPORTABLE_RELATIONSHIPS


def test_ungrounded_is_not_reportable():
    assert not is_reportable_relationship("UNGROUNDED")
