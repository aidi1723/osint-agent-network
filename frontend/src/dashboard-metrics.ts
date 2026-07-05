import type { Investigation } from "./types";

export type CockpitMetric = {
  label: string;
  value: string;
  tone?: "success" | "warning" | "danger";
};

export function cockpitBluf(selected: Investigation | null) {
  return selected?.summary?.trim() || "Agent 完成任务后会在这里回写摘要、实体、证据和关系。";
}

export function buildCockpitMetrics(selected: Investigation | null): CockpitMetric[] {
  if (!selected) {
    return [
      { label: "综合置信度", value: "-" },
      { label: "证据账本", value: "0" },
      { label: "事实池", value: "0" },
      { label: "缺口", value: "-" },
    ];
  }

  const gapCount = selected.graph?.summary.collection_gaps;

  return [
    {
      label: "综合置信度",
      value: selected.confidence === null ? "-" : selected.confidence.toFixed(2),
      tone: selected.confidence === null ? undefined : "success",
    },
    { label: "证据账本", value: String(selected.evidence_ledger?.length ?? 0) },
    { label: "事实池", value: String(selected.facts?.length ?? 0) },
    {
      label: "缺口",
      value: typeof gapCount === "number" ? String(gapCount) : "-",
      tone: typeof gapCount === "number" && gapCount > 0 ? "warning" : undefined,
    },
  ];
}
