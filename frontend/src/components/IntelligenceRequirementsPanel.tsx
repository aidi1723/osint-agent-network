import { coreV3StatusLabel } from "../core-v3";
import type { IntelligenceRequirements } from "../types";

export function IntelligenceRequirementsPanel({ requirements }: { requirements?: IntelligenceRequirements }) {
  const pirs = requirements?.pirs ?? [];
  const eeis = requirements?.eeis ?? [];
  return (
    <article className="core-v2-panel hcs-brief-card core-v3-panel">
      <div className="section-heading">
        <h3>PIR / EEI 情报需求</h3>
        <span>{pirs.length} PIR · {eeis.length} EEI</span>
      </div>
      <div className="core-v3-pir-list">
        {pirs.slice(0, 5).map((pir) => (
          <div key={pir.id} className={`core-v3-status status-${pir.status.toLowerCase()}`}>
            <strong>{coreV3StatusLabel(pir.status)}</strong>
            <span>{pir.question}</span>
          </div>
        ))}
        {!pirs.length ? <div className="empty compact">暂无 PIR，系统会按目标类型生成默认情报需求。</div> : null}
      </div>
      <div className="core-v3-chip-row">
        {eeis.slice(0, 10).map((eei) => (
          <span key={eei.id} className={`core-v3-chip status-${eei.status.toLowerCase()}`} title={eei.label}>
            {eei.required ? "*" : ""}{eei.label}: {coreV3StatusLabel(eei.status)}
          </span>
        ))}
      </div>
    </article>
  );
}
