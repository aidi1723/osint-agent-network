import { hypothesisStatusLabel } from "../core-v2";
import type { HypothesisAnalysis, HypothesisRecord } from "../types";
import { DataRow } from "./DataRow";

type HypothesisPanelProps = {
  hypotheses?: HypothesisRecord[];
  analysis?: HypothesisAnalysis;
};

export function HypothesisPanel({ hypotheses = [], analysis }: HypothesisPanelProps) {
  const sorted = [...hypotheses].sort((a, b) => {
    if (a.status === "MOST_LIKELY") return -1;
    if (b.status === "MOST_LIKELY") return 1;
    return a.inconsistency_score - b.inconsistency_score;
  });
  return (
    <article className="core-v2-panel">
      <div className="section-heading">
        <h3>ACH 假说池</h3>
        <span>{analysis?.most_likely_hypothesis || "未评分"}</span>
      </div>
      <div className="ach-strip">
        <span>触发指标 {analysis?.triggered_indicators?.length ?? 0}</span>
        <span>激活率 {Math.round((analysis?.indicator_activation_rate ?? 0) * 100)}%</span>
        <span>{analysis?.confidence_language || "置信语言待生成"}</span>
      </div>
      <div className="detail-stack">
        {sorted.map((item) => (
          <DataRow
            key={item.id}
            title={`${hypothesisStatusLabel(item.status)}：${item.statement}`}
            meta={`支持 ${item.support_score.toFixed(2)} / 矛盾 ${item.inconsistency_score.toFixed(2)} / ${item.mutually_exclusive_group}`}
            body={[
              item.supporting_evidence.length ? `支持证据：${item.supporting_evidence.join("、")}` : "",
              item.contradictory_evidence.length ? `反证：${item.contradictory_evidence.join("、")}` : "",
            ].filter(Boolean).join("\n")}
          />
        ))}
        {!sorted.length ? <div className="empty compact">暂无竞争性假说。</div> : null}
      </div>
    </article>
  );
}
