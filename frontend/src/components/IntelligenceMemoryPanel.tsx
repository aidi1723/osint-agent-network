import { labelOf, entityTypeLabels } from "../labels";
import type { IntelligenceMemory } from "../types";
import { DataRow } from "./DataRow";

type IntelligenceMemoryPanelProps = {
  memory?: IntelligenceMemory;
};

export function IntelligenceMemoryPanel({ memory }: IntelligenceMemoryPanelProps) {
  if (!memory) {
    return null;
  }
  const confirmed = memory.confirmed_findings ?? [];
  const gaps = memory.collection_gaps ?? [];
  const collection = memory.directed_collection ?? [];

  return (
    <article className="intel-memory-panel">
      <div className="section-heading">
        <h3>情报记忆与接力</h3>
        <span>{confirmed.length} 个确认点 / {gaps.length} 个缺口</span>
      </div>
      <div className="memory-stat-grid">
        <span>证据 {memory.coverage.evidence_items}</span>
        <span>关系 {memory.coverage.relationships}</span>
        <span>待复核 {memory.coverage.review_items}</span>
      </div>
      <div className="detail-stack">
        {confirmed.slice(0, 6).map((item) => (
          <DataRow
            key={`${item.type}:${item.value}`}
            title={`${labelOf(entityTypeLabels, item.type)}：${item.value}`}
            meta={`${item.source_tool} / ${item.confidence.toFixed(2)} / 证据 ${item.evidence_count ?? 0}`}
          />
        ))}
        {confirmed.length > 6 ? (
          <details className="compact-details">
            <summary>展开其余确认点 {confirmed.length - 6} 条</summary>
            {confirmed.slice(6).map((item) => (
              <DataRow
                key={`${item.type}:${item.value}`}
                title={`${labelOf(entityTypeLabels, item.type)}：${item.value}`}
                meta={`${item.source_tool} / ${item.confidence.toFixed(2)} / 证据 ${item.evidence_count ?? 0}`}
              />
            ))}
          </details>
        ) : null}
        {gaps.length ? (
          <details className="compact-details" open>
            <summary>下一步情报缺口 {gaps.length} 项</summary>
            {collection.map((item) => (
              <DataRow
                key={item.gap_key}
                title={item.agent_focus}
                meta={(item.related_jobs ?? []).length ? `关联队列：${(item.related_jobs ?? []).join("、")}` : "需要新一轮定向采集"}
                body={item.prompt}
              />
            ))}
          </details>
        ) : null}
      </div>
    </article>
  );
}
