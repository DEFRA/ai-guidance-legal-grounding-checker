import type { SourceFragmentRow } from "@/lib/law-statements-composition";

/** Refreshed structural fragments for WSI 2021/77 regulation 36 (offline verification fixture). */
export const WSI_2021_77_SOURCE_RECORD_ID = "lex-805b03f284dcf364";

export const wsi202177Regulation36Fragments: SourceFragmentRow[] = [
  {
    id: "frag-wsi77-reg-36",
    source_record_id: WSI_2021_77_SOURCE_RECORD_ID,
    locator: "regulation:36",
    fragment_text: "Regulation 36 applies to nitrogen accounting.",
  },
  {
    id: "frag-wsi77-reg-36-p1",
    source_record_id: WSI_2021_77_SOURCE_RECORD_ID,
    locator: "regulation:36:paragraph:1",
    fragment_text: "Paragraph one of regulation 36.",
    parent_fragment_id: "frag-wsi77-reg-36",
  },
  {
    id: "frag-wsi77-reg-36-p2",
    source_record_id: WSI_2021_77_SOURCE_RECORD_ID,
    locator: "regulation:36:paragraph:2",
    fragment_text: "Paragraph two of regulation 36.",
    parent_fragment_id: "frag-wsi77-reg-36",
  },
  {
    id: "frag-wsi77-reg-36-p3",
    source_record_id: WSI_2021_77_SOURCE_RECORD_ID,
    locator: "regulation:36:paragraph:3",
    fragment_text: "Paragraph three of regulation 36.",
    parent_fragment_id: "frag-wsi77-reg-36",
  },
  {
    id: "frag-wsi77-reg-36-p4",
    source_record_id: WSI_2021_77_SOURCE_RECORD_ID,
    locator: "regulation:36:paragraph:4",
    fragment_text:
      "The occupier must make a record of the calculations and how the final figures were arrived at.",
    parent_fragment_id: "frag-wsi77-reg-36",
  },
];
