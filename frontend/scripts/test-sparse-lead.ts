import assert from "node:assert/strict";

import { buildSparseLeadMetadata, parseLines, sparseLeadStages } from "../src/sparse-lead.ts";

assert.deepEqual(
  parseLines("Induction Cookers\n\n Gas Cooktops "),
  ["Induction Cookers", "Gas Cooktops"],
  "parseLines should trim blank textarea rows",
);

const metadata = buildSparseLeadMetadata({
  platform: "Alibaba",
  lead_display_name: "Long Way",
  member_id: "in19034126503jgqn",
  country_region: "IN",
  registration_year: "2023",
  company_name_raw: "Long Way",
  privacy_state: "email_phone_hidden",
  categoriesText: "Induction Cookers\nGas Cooktops",
  recentRfqsText: "2200W Electric Cook Top",
  operator_notes: "visible profile only",
});

assert.equal(metadata.platform, "Alibaba");
assert.deepEqual(metadata.categories, ["Induction Cookers", "Gas Cooktops"]);
assert.deepEqual(metadata.recent_rfqs, ["2200W Electric Cook Top"]);

const stages = sparseLeadStages([
  { tool_name: "lead_anchor_extraction", status: "COMPLETED" },
  { tool_name: "constrained_query_planning", status: "QUEUED" },
  { tool_name: "analysis_judgement", status: "QUEUED" },
]);

assert.equal(stages[0].label, "锚点提取");
assert.equal(stages[0].status, "COMPLETED");
assert.equal(stages[1].label, "约束检索");
assert.equal(stages.at(-1)?.label, "定向采集");

console.log("sparse lead helper checks passed");
