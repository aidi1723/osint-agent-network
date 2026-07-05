import assert from "node:assert/strict";
import type { FactRecord } from "../src/types.ts";
import {
  coreV3StatusLabel,
  factPromotionCounts,
  sortMatrixRows,
} from "../src/core-v3.ts";

const rows = sortMatrixRows([
  { field_key: "risk_signal", label: "风险", status: "MISSING", candidate_value: "", confidence: 0, supporting_sources: [], contradicting_sources: [], source_count: 0, independent_source_count: 0, linked_evidence_ids: [], linked_fact_ids: [], rationale: "" },
  { field_key: "company_identity", label: "企业", status: "CONFLICTED", candidate_value: "A", confidence: 0.2, supporting_sources: [], contradicting_sources: ["directory"], source_count: 1, independent_source_count: 1, linked_evidence_ids: [], linked_fact_ids: [], rationale: "" },
]);

assert.equal(coreV3StatusLabel("ACCEPTED_FACT"), "已采纳事实");
assert.equal(rows[0].field_key, "company_identity");
assert.deepEqual(
  factPromotionCounts([
    { promotion_stage: "ACCEPTED_FACT" },
    { promotion_stage: "CANDIDATE_FACT" },
    { promotion_stage: "CANDIDATE_FACT" },
  ] satisfies Partial<FactRecord>[]),
  { RAW_OBSERVATION: 0, CANDIDATE_FACT: 2, ASSESSED_FACT: 0, ACCEPTED_FACT: 1, REJECTED_FACT: 0 },
);

console.log("core v3 helper checks passed");
