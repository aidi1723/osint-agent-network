import { factStatusLabel, contactFacts } from "../core-v2";
import type { EvidenceLedgerRecord, FactRecord } from "../types";
import { DataRow } from "./DataRow";

type FactPoolPanelProps = {
  facts?: FactRecord[];
  evidenceLedger?: EvidenceLedgerRecord[];
};

export function FactPoolPanel({ facts = [], evidenceLedger = [] }: FactPoolPanelProps) {
  const contacts = contactFacts(facts);
  const evidenceById = new Map(evidenceLedger.map((item) => [item.id, item]));
  return (
    <article className="core-v2-panel">
      <div className="section-heading">
        <h3>事实池</h3>
        <span>{facts.length} 条 / 联系方式 {contacts.length} 条</span>
      </div>
      <div className="detail-stack">
        {contacts.length ? (
          <details className="compact-details" open>
            <summary>联系人与联系方式 {contacts.length} 条</summary>
            {contacts.map((fact) => (
              <FactRow key={fact.id} fact={fact} evidenceById={evidenceById} />
            ))}
          </details>
        ) : null}
        {facts.slice(0, 6).map((fact) => (
          <FactRow key={fact.id} fact={fact} evidenceById={evidenceById} />
        ))}
        {facts.length > 6 ? (
          <details className="compact-details">
            <summary>展开其余事实 {facts.length - 6} 条</summary>
            {facts.slice(6).map((fact) => (
              <FactRow key={fact.id} fact={fact} evidenceById={evidenceById} />
            ))}
          </details>
        ) : null}
        {!facts.length ? <div className="empty compact">暂无事实池记录。</div> : null}
      </div>
    </article>
  );
}

function FactRow({ fact, evidenceById }: { fact: FactRecord; evidenceById: Map<string, EvidenceLedgerRecord> }) {
  const sourceLabels = fact.evidence_ids
    .map((id) => evidenceById.get(id))
    .filter((item): item is EvidenceLedgerRecord => Boolean(item))
    .map((item) => `${item.source_tool} ${item.admiralty_code}`);
  return (
    <DataRow
      title={`${fact.subject} / ${fact.predicate} / ${fact.object}`}
      meta={`${factStatusLabel(fact.status)} / ${fact.confidence.toFixed(2)} / ${fact.admiralty_code || "未评级"}`}
      body={`${fact.statement}${sourceLabels.length ? `\n来源：${sourceLabels.join("、")}` : ""}`}
    />
  );
}
