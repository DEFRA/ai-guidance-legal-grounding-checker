"""Mirrored REPORTABLE_RELATIONSHIPS must not drift from the documented contract.

Canonical definition: proposition_matcher.matching.match_summary.REPORTABLE_RELATIONSHIPS.
Audit Assembler mirrors the set (no package dependency); this test pins both sides'
expected membership.
"""

from audit_assembler.match_summary import REPORTABLE_RELATIONSHIPS, is_reportable_relationship

# Keep identical to proposition_matcher.matching.match_summary.REPORTABLE_RELATIONSHIPS.
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
    for label in EXPECTED_REPORTABLE_RELATIONSHIPS:
        assert is_reportable_relationship(label)
    assert is_reportable_relationship("CONFLICT")  # normalises to CONFLICTS
