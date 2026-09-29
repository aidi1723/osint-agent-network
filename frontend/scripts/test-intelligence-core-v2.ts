import assert from "node:assert/strict";

import { contactFacts, coreV2Coverage, reportAuditItems } from "../src/core-v2.ts";
import type { EvidenceLedgerRecord, FactRecord, HypothesisRecord, IntelligenceMemory } from "../src/types.ts";

const facts: FactRecord[] = [
  {
    id: "fact-email",
    investigation_id: "inv-1",
    statement: "SRR uses xs@csituo.com as a public contact email.",
    subject: "SRR Genuine Parts",
    predicate: "uses_contact_email",
    object: "xs@csituo.com",
    status: "CONFIRMED",
    confidence: 0.82,
    admiralty_code: "A-2",
    evidence_ids: ["ev-1"],
    observed_at: "2026-05-21T00:00:00+00:00",
    valid_from: "2026-05-21T00:00:00+00:00",
  },
  {
    id: "fact-business",
    investigation_id: "inv-1",
    statement: "SRR sells auto parts across power, steering, brake and suspension systems.",
    subject: "SRR Genuine Parts",
    predicate: "has_product_scope",
    object: "Power, steering, brake and suspension systems",
    status: "CONFIRMED",
    confidence: 0.78,
    admiralty_code: "A-2",
    evidence_ids: ["ev-1"],
    observed_at: "2026-05-21T00:00:00+00:00",
    valid_from: "2026-05-21T00:00:00+00:00",
  },
];

const evidenceLedger: EvidenceLedgerRecord[] = [
  {
    id: "ev-1",
    investigation_id: "inv-1",
    source_url: "https://www.srrautopartsonline.com/en/",
    source_type: "official_website",
    source_tool: "official_web",
    snippet: "SRR contact page lists xs@csituo.com.",
    observed_at: "2026-05-21T00:00:00+00:00",
    admiralty_code: "A-2",
    source_reliability: "A",
    information_credibility: "2",
    content_hash: "1234567890abcdef",
  },
];

const hypotheses: HypothesisRecord[] = [
  {
    id: "h1",
    investigation_id: "inv-1",
    statement: "SRR is an active export brand network.",
    mutually_exclusive_group: "default",
    status: "MOST_LIKELY",
    support_score: 0.6,
    inconsistency_score: 0,
    supporting_evidence: ["ev-export"],
    contradictory_evidence: [],
    created_at: "2026-05-21T00:00:00+00:00",
    updated_at: "2026-05-21T00:00:00+00:00",
  },
];

const memory: IntelligenceMemory = {
  coverage: {
    confirmed_entities: 2,
    review_items: 0,
    collection_gaps: 2,
    evidence_items: 1,
    relationships: 0,
  },
  confirmed_findings: [],
  review_findings: [],
  collection_gaps: [
    { key: "decision_maker", label: "决策人", reason: "缺决策人" },
    { key: "news", label: "新闻/企业动态", reason: "缺新闻" },
  ],
  directed_collection: [],
};

assert.equal(contactFacts(facts).length, 1, "contact facts should be extracted from predicates and statements");
assert.deepEqual(coreV2Coverage(facts, evidenceLedger, hypotheses, memory), {
  facts: 2,
  confirmedFacts: 2,
  contacts: 1,
  evidenceLedger: 1,
  hypotheses: 1,
  gaps: 2,
});

const audit = reportAuditItems({
  facts,
  evidenceLedger,
  hypotheses,
  analysis: {
    most_likely_hypothesis: "h1",
    triggered_indicators: [],
    indicator_activation_rate: 0.2,
    confidence_language: "较可能",
  },
  memory,
  reportMarkdown: "# 报告",
});

assert.equal(audit.find((item) => item.key === "contacts")?.status, "ok");
assert.equal(audit.find((item) => item.key === "directed_collection")?.status, "review");

const missingAudit = reportAuditItems({
  facts: facts.filter((fact) => fact.id !== "fact-email"),
  evidenceLedger,
  hypotheses: [],
});
assert.equal(missingAudit.find((item) => item.key === "contacts")?.status, "missing");

console.log("intelligence core v2 frontend checks passed");
