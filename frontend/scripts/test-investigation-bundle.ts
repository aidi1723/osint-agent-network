import assert from "node:assert/strict";

import {
  combineGraphs,
  findDecisionProfileForInvestigation,
  isDecisionProfileInvestigation,
  visiblePrimaryInvestigations,
  type BundleInvestigation,
} from "../src/investigation-bundle.ts";

const enterprise: BundleInvestigation = {
  id: "buyer-family-hospitality-faiz-chaudhry",
  name: "美国企业背调：Family Hospitality LLC / Faiz Chaudhry",
  seed_value: "Family Hospitality LLC / Faiz Chaudhry",
  status: "NEEDS_REVIEW",
  graph: {
    nodes: [
      {
        id: "seed:target",
        label: "Family Hospitality LLC / Faiz Chaudhry",
        type: "seed",
        value: "Family Hospitality LLC / Faiz Chaudhry",
        source_tool: "investigation",
        confidence: 1,
        risk_level: "",
        evidence_count: 0,
        metadata: { seed_type: "username" },
      },
      {
        id: "entity:company",
        label: "Family Hospitality LLC",
        type: "entity",
        value: "Family Hospitality LLC",
        source_tool: "Alibaba 客户页截图",
        confidence: 0.86,
        risk_level: "",
        evidence_count: 1,
        metadata: { entity_type: "organization" },
      },
    ],
    edges: [
      {
        id: "edge:seed-company",
        from: "seed:target",
        to: "entity:company",
        label: "初始线索",
        type: "seed_matches_entity",
        confidence: 1,
        source: "investigation",
      },
    ],
    summary: { nodes: 2, edges: 1, risk_nodes: 0, evidence_nodes: 0, source_nodes: 0 },
  },
};

const decisionProfile: BundleInvestigation = {
  id: "decision-maker-faiz-chaudhry",
  name: "决策人画像：Faiz Chaudhry",
  seed_value: "Faiz Chaudhry",
  status: "NEEDS_REVIEW",
  graph: {
    nodes: [
      {
        id: "seed:target",
        label: "Faiz Chaudhry",
        type: "seed",
        value: "Faiz Chaudhry",
        source_tool: "investigation",
        confidence: 1,
        risk_level: "",
        evidence_count: 0,
        metadata: { seed_type: "username" },
      },
      {
        id: "entity:age",
        label: "年龄未确认",
        type: "entity",
        value: "年龄未确认",
        source_tool: "情报官复核规则",
        confidence: 0,
        risk_level: "",
        evidence_count: 1,
        metadata: { entity_type: "age_range" },
      },
    ],
    edges: [
      {
        id: "edge:seed-age",
        from: "seed:target",
        to: "entity:age",
        label: "公开年龄区间",
        type: "person_has_public_age_range",
        confidence: 0,
        source: "relationship",
      },
    ],
    summary: { nodes: 2, edges: 1, risk_nodes: 0, evidence_nodes: 0, source_nodes: 0 },
  },
};

assert.equal(isDecisionProfileInvestigation(decisionProfile), true);
assert.equal(isDecisionProfileInvestigation(enterprise), false);

assert.deepEqual(
  visiblePrimaryInvestigations([enterprise, decisionProfile]).map((item) => item.id),
  ["buyer-family-hospitality-faiz-chaudhry"],
  "decision-maker profiles should not appear as primary task-pool rows",
);

assert.equal(
  findDecisionProfileForInvestigation(enterprise, [enterprise, decisionProfile])?.id,
  "decision-maker-faiz-chaudhry",
  "the enterprise task should discover the matching decision-maker profile",
);

const combined = combineGraphs(enterprise.graph, decisionProfile.graph);

assert.equal(combined.summary.nodes, 4);
assert.equal(combined.summary.edges, 2);
assert.equal(
  combined.nodes.some((node) => node.value === "年龄未确认" && node.metadata.entity_type === "age_range"),
  true,
  "combined enterprise graph should include decision-maker personal attribute nodes",
);

console.log("investigation bundle checks passed");
