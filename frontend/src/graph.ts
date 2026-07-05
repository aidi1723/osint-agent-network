export type GraphNode = {
  id: string;
  label: string;
  type: "seed" | "entity" | "evidence" | "evidence_ledger" | "fact" | "hypothesis" | "risk_signal" | "source";
  value: string;
  source_tool: string;
  confidence: number;
  risk_level: string;
  evidence_count: number;
  metadata: Record<string, unknown>;
};

export type GraphEdge = {
  id: string;
  from: string;
  to: string;
  label: string;
  type: string;
  confidence: number;
  source: string;
  metadata?: Record<string, unknown>;
};

export type GraphPoint = {
  x: number;
  y: number;
  width: number;
  height: number;
  radius?: number;
  shape: "circle" | "rect";
};

export type GraphLayout = Map<string, GraphPoint> & {
  height: number;
  width: number;
};

export type GraphTemplateSlot = {
  id: string;
  label: string;
  zone: "evidence" | "main";
  x: number;
  y: number;
  width: number;
  height: number;
  shape: "circle" | "rect";
  matcher: (node: GraphNode) => boolean;
};

const TEMPLATE_NODE_PREFIX = "template:empty:";

const topEvidenceSlots = [
  { id: "evidence_top_1", x: 160, y: 92 },
  { id: "evidence_top_2", x: 410, y: 92 },
  { id: "evidence_top_3", x: 660, y: 92 },
  { id: "evidence_top_4", x: 910, y: 92 },
  { id: "evidence_top_5", x: 1160, y: 92 },
];

const bottomEvidenceSlots = [
  { id: "evidence_bottom_1", x: 160, y: 900 },
  { id: "evidence_bottom_2", x: 410, y: 900 },
  { id: "evidence_bottom_3", x: 660, y: 900 },
  { id: "evidence_bottom_4", x: 910, y: 900 },
  { id: "evidence_bottom_5", x: 1160, y: 900 },
];

export function graphTemplateSlots(): GraphTemplateSlot[] {
  const evidenceSlots = [...topEvidenceSlots, ...bottomEvidenceSlots].map((slot) => ({
    ...slot,
    label: "证据",
    zone: "evidence" as const,
    width: 214,
    height: 60,
    shape: "rect" as const,
    matcher: (node: GraphNode) => ["evidence", "evidence_ledger", "fact", "hypothesis"].includes(node.type),
  }));

  return [
    ...evidenceSlots,
    mainSlot("decision_name", "决策人姓名", 310, 275, (node) => entityTypeOf(node) === "identity"),
    mainSlot("decision_role", "身份/职位", 310, 395, isDecisionRoleSnippet),
    mainSlot("decision_contact", "决策人电话/邮箱", 310, 515, (node) => ["email", "phone"].includes(entityTypeOf(node)) && looksLikePersonalContact(node)),
    mainSlot("social_profile", "社媒/公开主页", 310, 635, (node) => ["social_profile", "platform_account", "username", "profile_url"].includes(entityTypeOf(node))),
    mainSlot("personal_habit", "性别/年龄/习惯", 310, 755, (node) =>
      ["gender_claim", "age_claim", "age_range", "dietary_preference", "hospitality_preference", "public_personal_attribute"].includes(entityTypeOf(node)),
    ),
    mainSlot("purchase_intent", "采购意图/需求匹配", 660, 275, isPurchaseIntentSnippet),
    mainSlot("core_clue", "核心线索", 660, 540, (node) => node.type === "seed", "circle"),
    mainSlot("upstream_downstream", "上下游/合作伙伴", 660, 755, (node) =>
      ["organization", "production_base"].includes(entityTypeOf(node)) || isManufacturingNetworkSnippet(node),
    ),
    mainSlot("company_name", "企业名称", 1010, 275, (node) => entityTypeOf(node) === "organization" || node.type === "seed"),
    mainSlot("business_scope", "主营业务/行业", 1010, 395, isBusinessScopeSnippet),
    mainSlot("company_website", "企业网址", 1010, 515, (node) =>
      ["domain", "subdomain", "url", "profile_url", "external_link", "ip"].includes(entityTypeOf(node))
      && metadataString(node, "core_axis") !== "decision_will",
    ),
    mainSlot("company_contact", "企业电话/邮箱", 1010, 635, (node) => ["phone", "email"].includes(entityTypeOf(node)) && !looksLikePersonalContact(node)),
    mainSlot("activity_region", "活动地区/常驻地区", 1010, 755, (node) => ["address", "declared_location", "likely_activity_region"].includes(entityTypeOf(node))),
  ];
};

function mainSlot(
  id: string,
  label: string,
  x: number,
  y: number,
  matcher: (node: GraphNode) => boolean,
  shape: "circle" | "rect" = "rect",
): GraphTemplateSlot {
  return {
    id,
    label,
    zone: "main",
    x,
    y,
    width: shape === "circle" ? 176 : 214,
    height: shape === "circle" ? 176 : 60,
    shape,
    matcher,
  };
}

export function nodeVisualGroup(node: GraphNode) {
  if (node.type !== "entity") {
    return node.type;
  }
  const entityType = typeof node.metadata.entity_type === "string" ? node.metadata.entity_type : "";
  if (["identity", "organization", "username", "platform_account", "social_profile"].includes(entityType)) {
    return "identity";
  }
  if (["email", "phone", "domain", "subdomain", "ip", "url", "profile_url", "external_link"].includes(entityType)) {
    return "contact";
  }
  if (
    [
      "age_claim",
      "age_range",
      "gender_claim",
      "public_personal_attribute",
      "dietary_preference",
      "hospitality_preference",
    ].includes(entityType)
  ) {
    return "personal";
  }
  return "metadata";
}

export function graphDisplayNodes(nodes: GraphNode[]) {
  const assigned = new Set<string>();
  const realNodes: GraphNode[] = [];
  const slots = graphTemplateSlots();
  for (const slot of slots.filter((item) => item.zone === "main")) {
    const match = nodes
      .filter((node) => !assigned.has(node.id))
      .filter(slot.matcher)
      .sort((a, b) => compareSlotNodePriority(slot.id, a, b))[0];
    if (match) {
      assigned.add(match.id);
      realNodes.push({ ...match, metadata: { ...match.metadata, template_slot: slot.id, template_label: slot.label } });
    } else {
      realNodes.push(emptyTemplateNode(slot));
    }
  }
  for (const slot of slots.filter((item) => item.zone === "evidence")) {
    const match = nodes
      .filter((node) => !assigned.has(node.id))
      .filter(slot.matcher)
      .sort((a, b) => compareSlotNodePriority(slot.id, a, b))[0];
    if (match) {
      assigned.add(match.id);
      realNodes.push({ ...match, metadata: { ...match.metadata, template_slot: slot.id, template_label: slot.label } });
    } else {
      realNodes.push(emptyTemplateNode(slot));
    }
  }
  return realNodes;
}

function compareSlotNodePriority(slotId: string, a: GraphNode, b: GraphNode) {
  return slotNodePriority(slotId, b) - slotNodePriority(slotId, a);
}

function slotNodePriority(slotId: string, node: GraphNode) {
  let score = nodePriority(node);
  const text = nodeSearchText(node);
  const slotHint = metadataString(node, "slot_hint");
  if (slotHint && slotHint === slotId) {
    score += 5;
  }
  if (slotId === "company_website" && slotHint === "digital-footprint") {
    score += 4;
  }
  if (slotId === "social_profile" && slotHint === "persona-role") {
    score += 4;
  }
  if (slotId === "company_name" && /(llc|ltd|inc|corp|co\.|company)/.test(text)) {
    score += 2;
  }
  if (slotId === "upstream_downstream" && /(investment|mart|exxon|group|supplier|partner|customer|distributor|retailer|convenience|base|factory|plant|manufactur|供应链|合作|基地|工厂|制造)/.test(text)) {
    score += 2;
  }
  if (slotId === "business_scope" && isBusinessScopeSnippet(node)) {
    score += 2;
  }
  if (slotId === "decision_role" && isDecisionRoleSnippet(node)) {
    score += 2;
  }
  if (slotId === "purchase_intent" && isPurchaseIntentSnippet(node)) {
    score += 2;
  }
  if (slotId === "core_clue" && node.type === "seed") {
    score += 3;
  }
  return score;
}

function emptyTemplateNode(slot: GraphTemplateSlot): GraphNode {
  return {
    id: `${TEMPLATE_NODE_PREFIX}${slot.id}`,
    label: "待补充",
    type: slot.zone === "evidence" ? "evidence" : "entity",
    value: "待补充",
    source_tool: "待补充",
    confidence: 0,
    risk_level: "",
    evidence_count: 0,
    metadata: {
      entity_type: "template_empty",
      evidence_kind: "template_empty",
      template_slot: slot.id,
      template_label: slot.label,
    },
  };
}

function compareNodePriority(a: GraphNode, b: GraphNode) {
  return nodePriority(b) - nodePriority(a);
}

function nodePriority(node: GraphNode) {
  const confidence = Number.isFinite(node.confidence) ? node.confidence : 0;
  const evidenceBoost = Math.min(0.2, node.evidence_count * 0.05);
  const typeBoost: Record<GraphNode["type"], number> = {
    seed: 1,
    entity: 0.5,
    evidence: 0.35,
    evidence_ledger: 0.4,
    fact: 0.55,
    hypothesis: 0.32,
    source: 0.2,
    risk_signal: 0.45,
  };
  const groupBoost: Record<string, number> = {
    identity: 0.25,
    contact: 0.2,
    personal: 0.12,
    metadata: 0.08,
  };
  return confidence + evidenceBoost + typeBoost[node.type] + (groupBoost[nodeVisualGroup(node)] ?? 0);
}

function entityTypeOf(node: GraphNode) {
  if (node.type !== "entity") {
    return node.type;
  }
  return typeof node.metadata.entity_type === "string" ? node.metadata.entity_type : "";
}

function metadataString(node: GraphNode, key: string) {
  const value = node.metadata[key];
  return typeof value === "string" ? value : "";
}

function factPredicateOf(node: GraphNode) {
  return typeof node.metadata.predicate === "string" ? node.metadata.predicate : "";
}

function nodeSearchText(node: GraphNode) {
  const metadataValues = [
    node.metadata.subject,
    node.metadata.predicate,
    node.metadata.object,
    node.metadata.status,
    node.metadata.source_type,
    node.metadata.snippet,
  ]
    .filter((value): value is string => typeof value === "string")
    .join(" ");
  return `${node.value} ${node.label} ${node.source_tool} ${metadataValues}`.toLowerCase();
}

function looksLikePersonalContact(node: GraphNode) {
  const text = nodeSearchText(node);
  return /decision|member manager|precision|personal|linkedin|social/.test(text);
}

function isDecisionRoleSnippet(node: GraphNode) {
  if (entityTypeOf(node) !== "bio_snippet" || isBusinessScopeSnippet(node)) {
    return false;
  }
  const text = nodeSearchText(node);
  return looksLikePersonalContact(node) || /(owner|founder|ceo|president|director|manager|buyer|procurement|采购|联系人|职位|role|l3)/.test(text);
}

function isBusinessScopeSnippet(node: GraphNode) {
  const entityType = entityTypeOf(node);
  if (["business_scope", "product_scope"].includes(entityType)) {
    return true;
  }
  if (node.type === "fact") {
    const predicate = factPredicateOf(node);
    return /(product|business|scope|market|coverage|scale|industry)/i.test(predicate);
  }
  if (entityType !== "bio_snippet" || looksLikePersonalContact(node)) {
    return false;
  }
  const text = nodeSearchText(node);
  return /(business|industry|retail|retailer|grocery|convenience|hospitality|investment|construction|estimate|estimating|oflc|h1bdata|perm|naics|sic|packager|labeler|product|service|主营|行业|业务)/.test(text);
}

function isManufacturingNetworkSnippet(node: GraphNode) {
  const entityType = entityTypeOf(node);
  if (["production_base", "organization"].includes(entityType)) {
    return true;
  }
  if (node.type !== "fact") {
    return false;
  }
  const predicate = factPredicateOf(node);
  const text = nodeSearchText(node);
  return /(base|branch|subsidiary|agent|partner|supply|manufactur|factory|network)/i.test(predicate)
    || /(base|factory|plant|manufactur|supplier|partner|agent|基地|工厂|制造|供应链|代理|合作|分公司)/.test(text);
}

function isPurchaseIntentSnippet(node: GraphNode) {
  const entityType = entityTypeOf(node);
  if (!["bio_snippet", "interest_tag", "public_personal_attribute"].includes(entityType)) {
    return false;
  }
  const text = nodeSearchText(node);
  return /(purchase|procurement|buyer|buying|sourcing|inquiry|demand|intent|fit|category|annual|rfq|quote|采购|询盘|需求|意图|匹配|品类|年采购|报价)/.test(text);
}

function nodeRank(node: GraphNode, degree: Map<string, number>) {
  const typeRank: Record<GraphNode["type"], number> = {
    seed: 0,
    entity: 1,
    evidence: 2,
    evidence_ledger: 2,
    fact: 2,
    hypothesis: 2,
    source: 3,
    risk_signal: 4,
  };
  return typeRank[node.type] * 100 - (degree.get(node.id) ?? 0);
}

function nodeSize(node: GraphNode, lane: GraphNode["type"]): Omit<GraphPoint, "x" | "y"> {
  const slot = slotForNode(node);
  if (slot) {
    return { width: slot.width, height: slot.height, shape: slot.shape };
  }
  if (node.type === "source") {
    return { width: 178, height: 52, shape: "rect" };
  }
  if (["evidence", "evidence_ledger", "fact", "hypothesis"].includes(node.type)) {
    return { width: 214, height: 60, shape: "rect" };
  }
  if (node.type === "risk_signal") {
    return { width: 206, height: 58, shape: "rect" };
  }
  if (lane === "entity") {
    return { width: 214, height: 58, shape: "rect" };
  }
  return { width: 160, height: 52, shape: "rect" };
}

function placeRow(
  points: GraphLayout,
  nodes: GraphNode[],
  startX: number,
  endX: number,
  y: number,
  lane: GraphNode["type"],
) {
  if (!nodes.length) {
    return;
  }
  nodes.forEach((node, index) => {
    const ratio = nodes.length === 1 ? 0.5 : index / (nodes.length - 1);
    const size = nodeSize(node, lane);
    points.set(node.id, {
      x: startX + (endX - startX) * ratio,
      y,
      ...size,
    });
  });
}

function placeColumn(
  points: GraphLayout,
  nodes: GraphNode[],
  x: number,
  startY: number,
  endY: number,
  lane: GraphNode["type"],
) {
  if (!nodes.length) {
    return;
  }
  nodes.forEach((node, index) => {
    const ratio = nodes.length === 1 ? 0.5 : index / (nodes.length - 1);
    const size = nodeSize(node, lane);
    points.set(node.id, {
      x,
      y: startY + (endY - startY) * ratio,
      ...size,
    });
  });
}

function spreadPositions(values: number[], minGap: number, min: number, max: number) {
  if (!values.length) {
    return [];
  }
  if (values.length === 1) {
    return [clamp(values[0], min, max)];
  }
  const available = max - min;
  if ((values.length - 1) * minGap > available) {
    return values.map((_, index) => min + (available / (values.length - 1)) * index);
  }
  const result = values.map((value) => clamp(value, min, max));
  for (let index = 1; index < result.length; index += 1) {
    result[index] = Math.max(result[index], result[index - 1] + minGap);
  }
  const overflow = result[result.length - 1] - max;
  if (overflow > 0) {
    for (let index = 0; index < result.length; index += 1) {
      result[index] -= overflow;
    }
  }
  return result.map((value) => clamp(value, min, max));
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function placeSourcesByConnections(
  points: GraphLayout,
  nodes: GraphNode[],
  edges: GraphEdge[],
) {
  const preferred = nodes
    .map((node, index) => {
      const relatedPoints = edges
        .filter((edge) => edge.from === node.id || edge.to === node.id)
        .map((edge) => points.get(edge.from === node.id ? edge.to : edge.from))
        .filter((point): point is GraphPoint => Boolean(point));
      const averageX = relatedPoints.length
        ? relatedPoints.reduce((sum, point) => sum + point.x, 0) / relatedPoints.length
        : 300 + index * 180;
      return { node, x: clamp(averageX, 260, 1060) };
    })
    .sort((a, b) => a.x - b.x);
  const rows = [920, 1000];
  const rowBuckets = [preferred.filter((_, index) => index % 2 === 0), preferred.filter((_, index) => index % 2 === 1)];
  rowBuckets.forEach((bucket, rowIndex) => {
    const adjusted = spreadPositions(bucket.map((item) => item.x), 178, 250, 1070);
    bucket.forEach((item, index) => {
      points.set(item.node.id, {
        x: adjusted[index],
        y: rows[rowIndex],
        ...nodeSize(item.node, "source"),
      });
    });
  });
}

function placeFixedColumn(
  points: GraphLayout,
  nodes: GraphNode[],
  x: number,
  ySlots: number[],
  lane: GraphNode["type"],
) {
  nodes.slice(0, ySlots.length).forEach((node, index) => {
    points.set(node.id, {
      x,
      y: ySlots[index],
      ...nodeSize(node, lane),
    });
  });
}

function hashNumber(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

export function layoutEvidenceMap(nodes: GraphNode[], edges: GraphEdge[]) {
  const points = new Map<string, GraphPoint>() as GraphLayout;
  const width = 1320;
  const height = 980;
  for (const node of nodes) {
    const slot = slotForNode(node);
    if (!slot) {
      continue;
    }
    points.set(node.id, {
      x: slot.x,
      y: slot.y,
      width: slot.width,
      height: slot.height,
      shape: slot.shape,
    });
  }

  points.width = width;
  points.height = height;
  return points;
}

function slotForNode(node: GraphNode) {
  const slotId = typeof node.metadata.template_slot === "string" ? node.metadata.template_slot : "";
  return graphTemplateSlots().find((slot) => slot.id === slotId);
}

export function edgeEndpoints(from: GraphPoint, to: GraphPoint) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.max(1, Math.hypot(dx, dy));
  return {
    from: shiftPoint(from, dx / distance, dy / distance),
    to: shiftPoint(to, -dx / distance, -dy / distance),
  };
}

function shiftPoint(point: GraphPoint, ux: number, uy: number) {
  if (point.shape === "circle") {
    const radius = point.radius ?? Math.min(point.width, point.height) / 2;
    return { x: point.x + ux * radius, y: point.y + uy * radius };
  }
  const scale = Math.min(
    Math.abs((point.width / 2) / (ux || 0.0001)),
    Math.abs((point.height / 2) / (uy || 0.0001)),
  );
  return { x: point.x + ux * scale, y: point.y + uy * scale };
}

export function curvedEdgePath(from: { x: number; y: number }, to: { x: number; y: number }, id = "") {
  const midX = (from.x + to.x) / 2;
  const midY = (from.y + to.y) / 2;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.max(1, Math.hypot(dx, dy));
  const direction = hashNumber(id) % 2 === 0 ? 1 : -1;
  const bend = Math.min(46, distance * 0.1) * direction;
  const controlX = midX - (dy / distance) * bend;
  const controlY = midY + (dx / distance) * bend;
  return `M ${from.x} ${from.y} Q ${controlX} ${controlY} ${to.x} ${to.y}`;
}

export function edgeLabelPoint(from: { x: number; y: number }, to: { x: number; y: number }, id: string) {
  const midX = (from.x + to.x) / 2;
  const midY = (from.y + to.y) / 2;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.max(1, Math.hypot(dx, dy));
  const direction = hashNumber(id) % 2 === 0 ? 1 : -1;
  const offset = Math.min(28, distance * 0.06) * direction;
  return {
    x: midX - (dy / distance) * offset,
    y: midY + (dx / distance) * offset,
  };
}

export function graphVisibleEdges(edges: GraphEdge[], nodes: GraphNode[]) {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const drawableNodeIds = new Set(nodes.filter((node) => !node.id.startsWith(TEMPLATE_NODE_PREFIX)).map((node) => node.id));
  const evidenceTargets = new Set<string>();
  const supportingSources = new Set<string>();

  for (const edge of edges) {
    if (edge.type === "supports_entity") {
      evidenceTargets.add(edge.to);
    }
    if (edge.type === "source_emitted_evidence" || edge.type === "supports_relationship") {
      supportingSources.add(edge.from);
    }
  }

  const keptSourceTargets = new Set<string>();
  const relationshipSupportBest = new Map<string, GraphEdge>();

  for (const edge of edges) {
    if (edge.type !== "supports_relationship") {
      continue;
    }
    const supportKey = `${edge.from}:${edge.to}`;
    const current = relationshipSupportBest.get(supportKey);
    if (!current || edge.confidence > current.confidence) {
      relationshipSupportBest.set(supportKey, edge);
    }
  }

  return edges.filter((edge) => {
    if (!drawableNodeIds.has(edge.from) || !drawableNodeIds.has(edge.to)) {
      return false;
    }
    if (edge.type === "source_emitted_entity") {
      const sourceNode = nodeById.get(edge.from);
      const targetNode = nodeById.get(edge.to);
      const hasStructuredSupport = evidenceTargets.has(edge.to) || supportingSources.has(edge.from);
      if (hasStructuredSupport) {
        return false;
      }
      const sourceKey = `${edge.from}:${sourceNode?.source_tool || edge.source}:${targetNode ? nodeVisualGroup(targetNode) : edge.to}`;
      if (keptSourceTargets.has(sourceKey)) {
        return false;
      }
      keptSourceTargets.add(sourceKey);
      return true;
    }

    if (edge.type === "supports_relationship") {
      return relationshipSupportBest.get(`${edge.from}:${edge.to}`)?.id === edge.id;
    }

    return true;
  });
}

export function edgeTone(edge: GraphEdge, nodes: GraphNode[]) {
  if (edge.type.includes("source")) {
    return "source";
  }
  if (edge.type.includes("risk")) {
    return "risk";
  }
  if (edge.type.includes("evidence") || edge.type.includes("supports")) {
    return "evidence";
  }
  const target = nodes.find((node) => node.id === edge.to);
  if (target?.type === "source") {
    return "source";
  }
  if (target?.type === "risk_signal") {
    return "risk";
  }
  return "entity";
}

export function shouldShowEdgeLabel(edge: GraphEdge) {
  if (edge.type === "source_emitted_entity") {
    return false;
  }
  if (edge.type === "source_emitted_evidence") {
    return false;
  }
  return true;
}

export function edgeStrokeWidth(_edge: GraphEdge, _tone: string) {
  return 0.45;
}
