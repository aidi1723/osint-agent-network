import type { EvidenceLedgerRecord } from "../types";
import { DataRow } from "./DataRow";

type EvidenceLedgerPanelProps = {
  evidenceLedger?: EvidenceLedgerRecord[];
};

export function EvidenceLedgerPanel({ evidenceLedger = [] }: EvidenceLedgerPanelProps) {
  return (
    <article className="core-v2-panel">
      <div className="section-heading">
        <h3>证据账本</h3>
        <span>{evidenceLedger.length} 条</span>
      </div>
      <div className="detail-stack">
        {evidenceLedger.slice(0, 6).map((item) => (
          <DataRow
            key={item.id}
            title={item.source_url}
            meta={`${item.source_tool} / ${item.source_type} / ${item.admiralty_code} / ${item.content_hash}`}
            body={item.snippet}
          />
        ))}
        {evidenceLedger.length > 6 ? (
          <details className="compact-details">
            <summary>展开其余证据账本 {evidenceLedger.length - 6} 条</summary>
            {evidenceLedger.slice(6).map((item) => (
              <DataRow
                key={item.id}
                title={item.source_url}
                meta={`${item.source_tool} / ${item.source_type} / ${item.admiralty_code} / ${item.content_hash}`}
                body={item.snippet}
              />
            ))}
          </details>
        ) : null}
        {!evidenceLedger.length ? <div className="empty compact">暂无证据账本记录。</div> : null}
      </div>
    </article>
  );
}
