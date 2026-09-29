import { describe, expect, it } from "vitest";
import { buildCockpitMetrics, cockpitBluf } from "./dashboard-metrics";
import type { Entity, EvidenceLedgerRecord, FactRecord, Investigation, Relationship } from "./types";

function investigation(overrides: Partial<Investigation> = {}): Investigation {
  return {
    id: "inv-1",
    name: "example.com 深度调查",
    seed_type: "domain",
    seed_value: "example.com",
    strategy: "deep",
    status: "COMPLETED",
    created_at: "2026-05-21T00:00:00Z",
    claimed_by_agent_name: null,
    summary: "BLUF: 主体与数字足迹存在明显冲突。",
    report_markdown: "",
    confidence: 0.82,
    max_depth: 3,
    max_jobs: 20,
    max_entities: 100,
    entities: [{ id: "e1" } as Entity],
    facts: [{ id: "f1" } as FactRecord, { id: "f2" } as FactRecord],
    evidence: [],
    evidence_ledger: [
      { id: "l1" } as EvidenceLedgerRecord,
      { id: "l2" } as EvidenceLedgerRecord,
      { id: "l3" } as EvidenceLedgerRecord,
    ],
    relationships: [{ id: "r1" } as Relationship],
    hypotheses: [],
    jobs: [],
    job_counts: {},
    graph: {
      nodes: [],
      edges: [],
      summary: {
        nodes: 0,
        edges: 0,
        evidence_nodes: 0,
        source_nodes: 0,
        risk_nodes: 0,
        collection_gaps: 4,
        memory_findings: 0,
      },
    },
    ...overrides,
  };
}

describe("dashboard metrics", () => {
  it("returns placeholder metrics when no investigation is selected", () => {
    expect(buildCockpitMetrics(null)).toEqual([
      { label: "综合置信度", value: "-" },
      { label: "证据账本", value: "0" },
      { label: "事实池", value: "0" },
      { label: "缺口", value: "-" },
    ]);
  });

  it("derives compact metrics from selected investigation data", () => {
    expect(buildCockpitMetrics(investigation())).toEqual([
      { label: "综合置信度", value: "0.82", tone: "success" },
      { label: "证据账本", value: "3" },
      { label: "事实池", value: "2" },
      { label: "缺口", value: "4", tone: "warning" },
    ]);
  });

  it("uses a dash for null confidence and missing graph gaps", () => {
    expect(buildCockpitMetrics(investigation({ confidence: null, graph: undefined }))).toEqual([
      { label: "综合置信度", value: "-" },
      { label: "证据账本", value: "3" },
      { label: "事实池", value: "2" },
      { label: "缺口", value: "-" },
    ]);
  });

  it("uses selected summary as BLUF and falls back to waiting copy", () => {
    expect(cockpitBluf(investigation())).toBe("BLUF: 主体与数字足迹存在明显冲突。");
    expect(cockpitBluf(investigation({ summary: "" }))).toBe("Agent 完成任务后会在这里回写摘要、实体、证据和关系。");
  });
});
