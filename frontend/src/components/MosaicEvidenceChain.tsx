import type { Entity, EvidenceItem, Relationship } from "../types";

type MosaicEvidenceChainProps = {
  entities?: Entity[];
  evidence?: EvidenceItem[];
  relationships?: Relationship[];
};

const osintTools = new Set(["amass", "spiderfoot", "sherlock"]);

function statusFor(entity: Entity) {
  if (entity.confidence >= 0.7) {
    return "confirmed";
  }
  return "candidate";
}

function slotFor(entity: Entity) {
  if (entity.source_tool === "amass") {
    return "组织资产核 / 数字外延";
  }
  if (entity.source_tool === "sherlock") {
    return "意志决策核 / 公开主页候选";
  }
  if (entity.type === "email") {
    return "桥接链 / 联系方式";
  }
  if (["company", "domain", "subdomain", "ip", "url"].includes(entity.type)) {
    return "组织资产核 / 被动富集";
  }
  return "意志决策核 / 候选画像";
}

function evidenceFor(entity: Entity, evidence: EvidenceItem[]) {
  return evidence.find((item) => item.entity_value === entity.value);
}

function triggerFor(entity: Entity, relationships: Relationship[]) {
  const relationship = relationships.find((item) => item.to_value === entity.value);
  if (!relationship) {
    return "seed -> finding";
  }
  return `${relationship.from_value} -> ${relationship.relationship_type}`;
}

export function MosaicEvidenceChain({ entities = [], evidence = [], relationships = [] }: MosaicEvidenceChainProps) {
  const rows = entities
    .filter((entity) => osintTools.has(entity.source_tool))
    .slice()
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 8)
    .map((entity) => ({
      entity,
      evidence: evidenceFor(entity, evidence),
      trigger: triggerFor(entity, relationships),
      status: statusFor(entity),
      slot: slotFor(entity),
    }));

  return (
    <article className="mosaic-chain-panel">
      <div className="section-heading">
        <h3>马赛克证据链</h3>
        <span>{rows.length} 条</span>
      </div>
      <div className="mosaic-chain-list">
        {rows.map((row) => (
          <div key={`${row.entity.source_tool}:${row.entity.type}:${row.entity.value}`} className={`mosaic-chain-row is-${row.status}`}>
            <div className="mosaic-chain-head">
              <strong>{row.entity.source_tool}</strong>
              <span>{row.slot}</span>
              <em>{row.status === "confirmed" ? "已确认" : "候选待核"}</em>
            </div>
            <p>{row.entity.type}: {row.entity.value}</p>
            <small>{row.trigger}</small>
            <small>{row.evidence?.snippet ?? row.evidence?.evidence_kind ?? "暂无证据片段，等待工具回写补齐。"}</small>
          </div>
        ))}
        {!rows.length ? <div className="empty compact">暂无 Amass / SpiderFoot / Sherlock 证据链。</div> : null}
      </div>
    </article>
  );
}
