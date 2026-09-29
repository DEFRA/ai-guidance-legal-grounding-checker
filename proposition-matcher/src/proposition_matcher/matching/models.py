# Pair-level relationship vocabulary. A single guidance proposition is judged
# against each surviving law candidate as exactly one of these.
#
# ``relationship`` is always pair-level (one guidance–law comparison). Do not
# add pipeline/coverage values here (e.g. "no law candidate") — those belong on
# ``GuidancePropositionMatchSummary`` / ``match_processing`` (see match_summary.py).
# ``UNGROUNDED`` means the candidate pair was evaluated and rejected; it is kept
# for audit, not as a reportable UI comparison row.
RELATIONSHIP_TYPES = (
    "GROUNDED",             # guidance accurately reflects this law
    "UNGROUNDED",           # this law is not the right basis for the guidance
    "CONFLICTS",            # guidance contradicts this law (same framework)
    "GUIDANCE_INCOMPLETE",  # guidance covers only part of what this law requires
    "GUIDANCE_BROADER",     # guidance adds requirements beyond / above this law
    "GUIDANCE_MISSING",     # law states a requirement the guidance touches but skips
)
