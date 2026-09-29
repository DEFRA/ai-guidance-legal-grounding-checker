import type { ReviewStatus, StatementVerdict } from "@/lib/review-workbench-state";

export const RW_CHIP = "rw-chip";
export const RW_CHIP_WARN = "rw-chip-warn";
export const RW_STAGE_LABEL = "rw-stage-label";
export const RW_STAGE_LABEL_ON_DARK = "rw-stage-label-on-dark";
export const RW_LEGAL_EXCERPT = "rw-legal-excerpt";
export const RW_PANEL_HIGHLIGHT = "rw-panel-highlight";
export const RW_JOURNEY_ARROW = "rw-journey-arrow";

export const RW_SECTION_HEADER_STATUS: Record<ReviewStatus, string> = {
  unreviewed: "rw-section-header-status rw-section-header-status-unreviewed",
  draft_review: "rw-section-header-status rw-section-header-status-draft",
  complete_review: "rw-section-header-status rw-section-header-status-complete",
};

export const RW_VERDICT_BUTTON_CLASS: Record<StatementVerdict, string> = {
  accurate: "rw-verdict-btn rw-verdict-btn-accurate",
  incomplete: "rw-verdict-btn rw-verdict-btn-incomplete",
  overreaching: "rw-verdict-btn rw-verdict-btn-overreaching",
  bad_merge: "rw-verdict-btn rw-verdict-btn-bad_merge",
  missing_propositions: "rw-verdict-btn rw-verdict-btn-missing_propositions",
};

export function verdictButtonClass(verdict: StatementVerdict, active: boolean): string {
  const base = RW_VERDICT_BUTTON_CLASS[verdict];
  return active ? `${base} rw-verdict-btn-active` : `${base} rw-verdict-btn-idle`;
}

export function toggleButtonClass(active: boolean, compact = false): string {
  const size = compact ? "px-2 py-0.5 text-[11px]" : "px-2 py-1 text-[12px]";
  return `${size} font-medium ${active ? "rw-btn-toggle-active" : "rw-btn-toggle-idle"}`;
}
