import { coreV3StatusLabel, factPromotionCounts, promotionStageOrder } from "../core-v3";
import type { FactRecord } from "../types";

export function FactPromotionPanel({ facts }: { facts?: FactRecord[] }) {
  const counts = factPromotionCounts(facts ?? []);
  const accepted = (facts ?? []).filter((fact) => fact.promotion_stage === "ACCEPTED_FACT" || fact.status === "CONFIRMED").slice(0, 4);
  return (
    <article className="core-v2-panel hcs-brief-card core-v3-panel">
      <div className="section-heading">
        <h3>事实晋级</h3>
        <span>{facts?.length ?? 0} 条</span>
      </div>
      <div className="core-v3-chip-row">
        {promotionStageOrder.map((stage) => (
          <span key={stage} className={`core-v3-chip status-${stage.toLowerCase()}`}>
            {coreV3StatusLabel(stage)} {counts[stage]}
          </span>
        ))}
      </div>
      <div className="detail-stack compact-stack">
        {accepted.map((fact) => (
          <div key={fact.id} className="core-v3-fact-line">
            <strong>{coreV3StatusLabel(fact.promotion_stage ?? "CANDIDATE_FACT")}</strong>
            <span>{fact.statement}</span>
          </div>
        ))}
        {!accepted.length ? <div className="empty compact">暂无已采纳事实。</div> : null}
      </div>
    </article>
  );
}
