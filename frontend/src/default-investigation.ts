import type { Investigation } from "./types";

const REVIEW_READY_STATUSES = new Set(["NEEDS_REVIEW", "COMPLETED", "PARTIAL_FAILED"]);

export function chooseDefaultInvestigation(investigations: Investigation[]) {
  const reportable = investigations.filter(hasReportableContent).sort(compareNewestFirst);
  return reportable.find((item) => REVIEW_READY_STATUSES.has(item.status)) ?? reportable[0] ?? investigations.slice().sort(compareNewestFirst)[0];
}

function hasReportableContent(investigation: Investigation) {
  return Boolean(investigation.report_markdown?.trim() || investigation.summary?.trim() || investigation.confidence !== null);
}

function compareNewestFirst(a: Investigation, b: Investigation) {
  return timestampOf(b) - timestampOf(a);
}

function timestampOf(investigation: Investigation) {
  return Date.parse(investigation.updated_at ?? investigation.created_at) || 0;
}
