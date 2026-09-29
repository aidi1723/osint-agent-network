import type { GraphEdge, GraphNode } from "./graph";

export type BundleGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  summary: {
    nodes: number;
    edges: number;
    risk_nodes: number;
    evidence_nodes: number;
    source_nodes?: number;
    memory_findings?: number;
    collection_gaps?: number;
  };
};

export type BundleInvestigation = {
  id: string;
  name: string;
  seed_value: string;
  status: string;
  graph?: BundleGraph;
};

export function isDecisionProfileInvestigation(investigation: Pick<BundleInvestigation, "id" | "name">) {
  return investigation.id.startsWith("decision-maker-") || investigation.name.startsWith("决策人画像：");
}

export function visiblePrimaryInvestigations<T extends BundleInvestigation>(investigations: T[]) {
  return investigations.filter((investigation) => !isDecisionProfileInvestigation(investigation));
}

export function findDecisionProfileForInvestigation<T extends BundleInvestigation>(
  investigation: T | null,
  investigations: T[],
) {
  if (!investigation || isDecisionProfileInvestigation(investigation)) {
    return null;
  }
  const normalizedHaystack = normalizeForMatch(`${investigation.name} ${investigation.seed_value}`);
  return (
    investigations.find((candidate) => {
      if (!isDecisionProfileInvestigation(candidate)) {
        return false;
      }
      const profileName = normalizeForMatch(candidate.seed_value || candidate.name.replace("决策人画像：", ""));
      return Boolean(profileName) && normalizedHaystack.includes(profileName);
    }) ?? null
  );
}

export function combineGraphs(primary?: BundleGraph, decisionProfile?: BundleGraph): BundleGraph | undefined {
  if (!primary) {
    return decisionProfile;
  }
  if (!decisionProfile) {
    return primary;
  }
  const mergedDecisionGraph = namespaceDecisionProfileSeed(decisionProfile);
  const nodes = dedupeById([...primary.nodes, ...mergedDecisionGraph.nodes]);
  const edges = dedupeById([...primary.edges, ...mergedDecisionGraph.edges]);
  return {
    nodes,
    edges,
    summary: {
      nodes: nodes.length,
      edges: edges.length,
      risk_nodes: nodes.filter((node) => node.type === "risk_signal").length,
      evidence_nodes: nodes.filter((node) => node.type === "evidence").length,
      source_nodes: nodes.filter((node) => node.type === "source").length,
      memory_findings: (primary.summary.memory_findings ?? 0) + (mergedDecisionGraph.summary.memory_findings ?? 0),
      collection_gaps: (primary.summary.collection_gaps ?? 0) + (mergedDecisionGraph.summary.collection_gaps ?? 0),
    },
  };
}

function namespaceDecisionProfileSeed(graph: BundleGraph): BundleGraph {
  const seedNode = graph.nodes.find((node) => node.id === "seed:target");
  if (!seedNode) {
    return graph;
  }
  const seedId = "decision-profile:seed";
  return {
    ...graph,
    nodes: graph.nodes.map((node) =>
      node.id === "seed:target"
        ? {
            ...node,
            id: seedId,
            label: `决策人：${node.label}`,
            metadata: { ...node.metadata, seed_type: "decision_profile" },
          }
        : node,
    ),
    edges: graph.edges.map((edge) => ({
      ...edge,
      from: edge.from === "seed:target" ? seedId : edge.from,
      to: edge.to === "seed:target" ? seedId : edge.to,
    })),
  };
}

function dedupeById<T extends { id: string }>(items: T[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) {
      return false;
    }
    seen.add(item.id);
    return true;
  });
}

function normalizeForMatch(value: string) {
  return value
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}]+/gu, " ")
    .trim();
}
