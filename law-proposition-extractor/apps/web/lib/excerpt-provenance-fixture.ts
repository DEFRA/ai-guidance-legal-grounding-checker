/**
 * Real corruption exemplar from Wales WSI 2021 Schedule 1A paragraph 18
 * (export: slurry-gb-principal-5-one-shot-current-2-export, frag-lex-805b03f284dcf364-071).
 */
/** Verbatim from `source_fragments.json` frag-lex-805b03f284dcf364-071. */
export const SCHEDULE_1A_PARA_18_CORRUPTED_FRAGMENT_TEXT =
  "181The occupier must—amake a record of the type and amount of livestock manure (tonnes or cubic metres as applicable) that is intended to be sent off the holding during the relevant period, andbassess and record the amount of nitrogen (kg) in the livestock manure recorded under paragraph (a) in accordance with regulation 36(4) and Parts 1 and 2 of Schedule 3.2The records to be made under sub-paragraph (1) must be made by 1 March 2024.";

/** Same failure mode as fragment flattening when inline XML splits a token. */
export const INTERNAL_WORD_SPACE_EXAMPLE = "livestock m anure";

/** Canonical text after legislation.gov.uk XML is rendered with structural spacing. */
export const SCHEDULE_1A_PARA_18_CANONICAL_FRAGMENT_TEXT =
  "18.(1) The occupier must—(a) make a record of the type and amount of livestock manure (tonnes or cubic metres as applicable) that is intended to be sent off the holding during the relevant period, and (b) assess and record the amount of nitrogen (kg) in the livestock manure recorded under paragraph (a) in accordance with regulation 36(4) and Parts 1 and 2 of Schedule 3. (2) The records to be made under sub-paragraph (1) must be made by 1 March 2024.";

export const SCHEDULE_1A_PARA_18_FIXTURE = {
  statementId: "lawstmt:76ca05f0819bcc2f",
  propositionId: "prop:bcf538e48efe0715",
  sourceRecordId: "lex-805b03f284dcf364",
  fragmentId: "frag-lex-805b03f284dcf364-071",
  fragmentLocator: "schedule:1a:paragraph:18",
  statementText:
    "The occupier must make a record of the type and amount of livestock manure (tonnes or cubic metres as applicable) that is intended to be sent off the holding during the relevant period.",
  propositionText:
    "The occupier must make a record of the type and amount of livestock manure (tonnes or cubic metres as applicable) that is intended to be sent off the holding during the relevant period.",
  corruptedFragmentText: SCHEDULE_1A_PARA_18_CORRUPTED_FRAGMENT_TEXT,
  corruptedEvidenceQuote:
    "The occupier must—amake a record of the type and amount of livestock manure (tonnes or cubic metres as applicable) that is intended to be sent off the holding during the relevant period",
  corruptedRecipeExcerpt: "181The occupier must",
} as const;
