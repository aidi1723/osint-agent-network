import assert from "node:assert/strict";

import {
  edgeStrokeWidth,
  graphDisplayNodes,
  graphTemplateSlots,
  graphVisibleEdges,
  nodeVisualGroup,
  shouldShowEdgeLabel,
  type GraphEdge,
  type GraphNode,
} from "../src/graph.ts";

const nodes: GraphNode[] = [
  {
    id: "source:official",
    label: "official-website",
    type: "source",
    value: "official-website",
    source_tool: "official-website",
    confidence: 0,
    risk_level: "",
    evidence_count: 0,
    metadata: {},
  },
  {
    id: "source:linkedin",
    label: "linkedin-public-signal",
    type: "source",
    value: "linkedin-public-signal",
    source_tool: "linkedin-public-signal",
    confidence: 0,
    risk_level: "",
    evidence_count: 0,
    metadata: {},
  },
  {
    id: "entity:person",
    label: "Juan Carlos Aragon Diaz",
    type: "entity",
    value: "Juan Carlos Aragon Diaz",
    source_tool: "codex-public-osint",
    confidence: 0.96,
    risk_level: "",
    evidence_count: 2,
    metadata: { entity_type: "identity" },
  },
  {
    id: "entity:email",
    label: "jcaragon@aragonaluminio.com",
    type: "entity",
    value: "jcaragon@aragonaluminio.com",
    source_tool: "public-business-directory",
    confidence: 0.92,
    risk_level: "",
    evidence_count: 1,
    metadata: { entity_type: "email" },
  },
  {
    id: "entity:other",
    label: "Alexandra Luna",
    type: "entity",
    value: "Alexandra Luna",
    source_tool: "linkedin-public-signal",
    confidence: 0.55,
    risk_level: "",
    evidence_count: 0,
    metadata: { entity_type: "identity" },
  },
  {
    id: "evidence:person",
    label: "Official site confirms manager role",
    type: "evidence",
    value: "Juan Carlos Aragon Diaz",
    source_tool: "official-website",
    confidence: 0,
    risk_level: "",
    evidence_count: 0,
    metadata: { evidence_kind: "role_confirmation" },
  },
  {
    id: "entity:gender",
    label: "男性，公开称谓旁证",
    type: "entity",
    value: "男性，公开称谓旁证",
    source_tool: "public-profile",
    confidence: 0.65,
    risk_level: "",
    evidence_count: 1,
    metadata: { entity_type: "gender_claim" },
  },
  {
    id: "entity:age",
    label: "35-45，公开履历区间推断",
    type: "entity",
    value: "35-45，公开履历区间推断",
    source_tool: "career-timeline",
    confidence: 0.55,
    risk_level: "",
    evidence_count: 1,
    metadata: { entity_type: "age_range" },
  },
];

const edges: GraphEdge[] = [
  {
    id: "source-entity-person",
    from: "source:official",
    to: "entity:person",
    label: "信息来源",
    type: "source_emitted_entity",
    confidence: 0.96,
    source: "official-website",
  },
  {
    id: "source-entity-email",
    from: "source:official",
    to: "entity:email",
    label: "信息来源",
    type: "source_emitted_entity",
    confidence: 0.92,
    source: "official-website",
  },
  {
    id: "source-evidence-person",
    from: "source:official",
    to: "evidence:person",
    label: "信息来源",
    type: "source_emitted_evidence",
    confidence: 0,
    source: "official-website",
  },
  {
    id: "relationship-person-email",
    from: "entity:person",
    to: "entity:email",
    label: "uses_business_email",
    type: "uses_business_email",
    confidence: 0.92,
    source: "relationship",
  },
  {
    id: "support-relationship-a",
    from: "source:official",
    to: "entity:person",
    label: "关系来源",
    type: "supports_relationship",
    confidence: 0.92,
    source: "official-website",
    metadata: { relationship_edge_id: "relationship-person-email" },
  },
  {
    id: "support-relationship-b",
    from: "source:official",
    to: "entity:person",
    label: "关系来源",
    type: "supports_relationship",
    confidence: 0.96,
    source: "official-website",
    metadata: { relationship_edge_id: "relationship-person-company" },
  },
  {
    id: "support-entity-person",
    from: "evidence:person",
    to: "entity:person",
    label: "证据支持",
    type: "supports_entity",
    confidence: 0,
    source: "official-website",
  },
  {
    id: "orphan-source-entity",
    from: "source:linkedin",
    to: "entity:other",
    label: "信息来源",
    type: "source_emitted_entity",
    confidence: 0.55,
    source: "linkedin-public-signal",
  },
];

const visible = graphVisibleEdges(edges, nodes);
const visibleIds = new Set(visible.map((edge) => edge.id));

assert.equal(
  visibleIds.has("source-entity-person"),
  false,
  "sources with evidence-backed chains should not also draw direct source-to-entity lines",
);
assert.equal(
  visibleIds.has("source-entity-email"),
  false,
  "duplicate direct provenance lines should be removed when a clearer chain exists",
);
assert.equal(
  visibleIds.has("orphan-source-entity"),
  true,
  "sources without evidence or relationship support should keep one direct provenance line",
);
assert.equal(
  visible.filter((edge) => edge.type === "supports_relationship" && edge.from === "source:official" && edge.to === "entity:person").length,
  1,
  "relationship provenance lines should be deduplicated per source-target pair",
);
assert.equal(shouldShowEdgeLabel(edges[0]), false, "direct source lines should not render labels");
assert.equal(shouldShowEdgeLabel(edges[2]), false, "source-to-evidence lines should not render labels");
assert.equal(shouldShowEdgeLabel(edges[4]), true, "relationship provenance lines should keep their label");
assert.equal(nodeVisualGroup(nodes[6]), "personal", "public gender claims should render as personal attributes");
assert.equal(nodeVisualGroup(nodes[7]), "personal", "public age ranges should render as personal attributes");
assert.deepEqual(
  Array.from(new Set(edges.map((edge) => edgeStrokeWidth(edge, "entity")))),
  [0.45],
  "all graph edges should render as one very thin line weight",
);

const crowdedNodes: GraphNode[] = [
  ...nodes,
  ...Array.from({ length: 12 }, (_, index) => ({
    id: `entity:extra-contact-${index}`,
    label: `extra-contact-${index}`,
    type: "entity" as const,
    value: `extra-contact-${index}`,
    source_tool: "public-source",
    confidence: 0.4 + index / 100,
    risk_level: "",
    evidence_count: 0,
    metadata: { entity_type: "phone" },
  })),
  ...Array.from({ length: 8 }, (_, index) => ({
    id: `evidence:extra-${index}`,
    label: `extra-evidence-${index}`,
    type: "evidence" as const,
    value: `extra-evidence-${index}`,
    source_tool: "public-source",
    confidence: 0,
    risk_level: "",
    evidence_count: 0,
    metadata: { evidence_kind: "public_profile_metadata" },
  })),
];
const displayNodes = graphDisplayNodes(crowdedNodes);
assert.equal(
  displayNodes.filter((node) => node.type === "evidence").length,
  10,
  "graph canvas should reserve top and bottom evidence slots",
);
assert.equal(displayNodes.length, 23, "graph canvas should always render 10 evidence slots and 13 main information slots");
assert.equal(
  displayNodes.slice(0, 13).every((node) => node.metadata.template_slot !== "evidence_top_1" && node.metadata.template_slot !== "evidence_bottom_1"),
  true,
  "main information slots should be assigned before evidence slots consume fact nodes",
);
assert.equal(
  displayNodes.filter((node) => node.type === "source").length,
  0,
  "source nodes should be kept in folded provenance lists instead of occupying fixed canvas slots",
);
assert.equal(graphTemplateSlots().filter((slot) => slot.zone === "evidence").length, 10);
assert.equal(graphTemplateSlots().filter((slot) => slot.zone === "main").length, 13);
assert.equal(
  graphTemplateSlots().some((slot) => slot.label === "采购意图/需求匹配"),
  true,
  "fixed buyer profile template should expose purchase intent and demand fit",
);
assert.equal(
  graphTemplateSlots().some((slot) => slot.label === "主营业务/行业"),
  true,
  "fixed buyer profile template should expose the company's main business",
);
assert.equal(
  graphTemplateSlots().some((slot) => slot.label === "上下游/合作伙伴"),
  true,
  "fixed buyer profile template should expose upstream/downstream or partner context",
);
assert.equal(
  graphTemplateSlots().some((slot) => slot.label === "企业电话/邮箱"),
  true,
  "fixed buyer profile template should expose company contact channels",
);
assert.equal(
  graphTemplateSlots().some((slot) => slot.label === "决策人电话/邮箱"),
  true,
  "fixed buyer profile template should expose decision-maker contact channels",
);

const businessOnlyDisplayNodes = graphDisplayNodes([
  {
    id: "entity:business-scope",
    label: "Grocery and Convenience Retailers",
    type: "entity",
    value: "Grocery and Convenience Retailers",
    source_tool: "H1BData / OFLC public business profile",
    confidence: 0.76,
    risk_level: "",
    evidence_count: 1,
    metadata: { entity_type: "bio_snippet" },
  },
]);
const businessScopeNode = businessOnlyDisplayNodes.find((node) => node.metadata.template_slot === "business_scope");
const decisionRoleNode = businessOnlyDisplayNodes.find((node) => node.metadata.template_slot === "decision_role");
assert.equal(
  businessScopeNode?.value,
  "Grocery and Convenience Retailers",
  "company business scope snippets should populate the main business slot",
);
assert.equal(
  decisionRoleNode?.value,
  "待补充",
  "company business scope snippets should not be consumed by the decision-maker role slot",
);

const enterpriseDisplayNodes = graphDisplayNodes([
  {
    id: "entity:product-scope",
    label: "Power, transmission, suspension and brake systems",
    type: "entity",
    value: "Power, transmission, suspension and brake systems",
    source_tool: "official_web",
    confidence: 0.74,
    risk_level: "",
    evidence_count: 1,
    metadata: { entity_type: "product_scope" },
  },
  {
    id: "entity:production-base",
    label: "China Ningbo Cixi Shock Absorber Production Base",
    type: "entity",
    value: "China Ningbo Cixi Shock Absorber Production Base",
    source_tool: "official_web",
    confidence: 0.78,
    risk_level: "",
    evidence_count: 1,
    metadata: { entity_type: "production_base" },
  },
  {
    id: "entity:address",
    label: "No.65, Yinxing Street, Toutunhe Industrial Park, Urumqi, Xinjiang",
    type: "entity",
    value: "No.65, Yinxing Street, Toutunhe Industrial Park, Urumqi, Xinjiang",
    source_tool: "official_web",
    confidence: 0.84,
    risk_level: "",
    evidence_count: 1,
    metadata: { entity_type: "address" },
  },
]);
assert.equal(
  enterpriseDisplayNodes.find((node) => node.metadata.template_slot === "business_scope")?.value,
  "Power, transmission, suspension and brake systems",
  "product_scope should populate the main business slot",
);
assert.equal(
  enterpriseDisplayNodes.find((node) => node.metadata.template_slot === "upstream_downstream")?.value,
  "China Ningbo Cixi Shock Absorber Production Base",
  "production bases should remain available on the main enterprise graph",
);
assert.equal(
  enterpriseDisplayNodes.find((node) => node.metadata.template_slot === "activity_region")?.value,
  "No.65, Yinxing Street, Toutunhe Industrial Park, Urumqi, Xinjiang",
  "confirmed addresses should populate the activity region slot",
);

const coreV2FactDisplayNodes = graphDisplayNodes([
  {
    id: "entity:company",
    label: "SRR Genuine Parts / JAPAN SRR AUTO PARTS COMPANY LIMITED",
    type: "entity",
    value: "SRR Genuine Parts / JAPAN SRR AUTO PARTS COMPANY LIMITED",
    source_tool: "investigation",
    confidence: 1,
    risk_level: "",
    evidence_count: 0,
    metadata: { entity_type: "organization" },
  },
  {
    id: "fact:product-scope",
    label: "SRR 官网产品范围包括减震、悬挂、制动、传动和转向系统。",
    type: "fact",
    value: "SRR 官网产品范围包括减震、悬挂、制动、传动和转向系统。",
    source_tool: "fact_pool",
    confidence: 0.82,
    risk_level: "",
    evidence_count: 1,
    metadata: { predicate: "has_product_scope", object: "shock absorber; suspension; braking; transmission; steering" },
  },
  {
    id: "fact:base-list",
    label: "官网版制造/研发足迹包含嘉兴传动轴、江西球头摆臂等条目。",
    type: "fact",
    value: "官网版制造/研发足迹包含嘉兴传动轴、江西球头摆臂等条目。",
    source_tool: "fact_pool",
    confidence: 0.82,
    risk_level: "",
    evidence_count: 1,
    metadata: { predicate: "official_base_list", object: "Jiaxing CV Joint Axle; Jiangxi Ball Head Swing Arm" },
  },
  {
    id: "entity:contact",
    label: "0991-3966766 / 0991-3966788",
    type: "entity",
    value: "0991-3966766 / 0991-3966788",
    source_tool: "fact_pool",
    confidence: 0.86,
    risk_level: "",
    evidence_count: 1,
    metadata: { entity_type: "phone" },
  },
]);
assert.equal(
  coreV2FactDisplayNodes.find((node) => node.metadata.template_slot === "company_name")?.value,
  "SRR Genuine Parts / JAPAN SRR AUTO PARTS COMPANY LIMITED",
  "company seed should populate the company name slot when no organization entity exists",
);
assert.equal(
  coreV2FactDisplayNodes.find((node) => node.metadata.template_slot === "business_scope")?.id,
  "fact:product-scope",
  "Core v2 product facts should populate the main business slot",
);
assert.equal(
  coreV2FactDisplayNodes.find((node) => node.metadata.template_slot === "upstream_downstream")?.id,
  "fact:base-list",
  "Core v2 manufacturing-base facts should populate the upstream/downstream slot",
);
assert.equal(
  coreV2FactDisplayNodes.find((node) => node.metadata.template_slot === "company_contact")?.value,
  "0991-3966766 / 0991-3966788",
  "Core v2 contact fact objects should populate company contact once graph object nodes exist",
);

const osintNodes: GraphNode[] = [
  {
    id: "entity:subdomain",
    label: "vpn.example.com",
    type: "entity",
    value: "vpn.example.com",
    source_tool: "amass",
    confidence: 0.5,
    risk_level: "",
    evidence_count: 1,
    metadata: {
      entity_type: "subdomain",
      core_axis: "organization_asset",
      slot_hint: "digital-footprint",
      review_status: "candidate",
    },
  },
  {
    id: "entity:profile",
    label: "https://github.com/admin",
    type: "entity",
    value: "https://github.com/admin",
    source_tool: "sherlock",
    confidence: 0.35,
    risk_level: "",
    evidence_count: 1,
    metadata: {
      entity_type: "profile_url",
      core_axis: "decision_will",
      slot_hint: "persona-role",
      review_status: "candidate",
    },
  },
];

const osintDisplayNodes = graphDisplayNodes(osintNodes);
const subdomainSlot = osintDisplayNodes.find((node) => node.value === "vpn.example.com")?.metadata.template_slot;
const profileSlot = osintDisplayNodes.find((node) => node.value === "https://github.com/admin")?.metadata.template_slot;

assert.equal(subdomainSlot, "company_website", "OSINT digital-footprint domains should occupy the organization-side digital asset slot");
assert.equal(profileSlot, "social_profile", "Sherlock public-profile candidates should occupy the decision-side social profile slot");
assert.equal(nodeVisualGroup(osintNodes[0]), "contact", "subdomain findings should render as contact/digital assets");

console.log("graph helper checks passed");
