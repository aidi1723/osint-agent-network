import { coreV3StatusLabel, sortMatrixRows } from "../core-v3";
import type { CrossVerificationRow } from "../types";

export function CrossVerificationMatrixPanel({ rows }: { rows?: CrossVerificationRow[] }) {
  const sorted = sortMatrixRows(rows ?? []);
  return (
    <article className="core-v2-panel core-v3-panel core-v3-matrix-panel">
      <div className="section-heading">
        <h3>交叉验证矩阵</h3>
        <span>{sorted.length} 项</span>
      </div>
      <div className="core-v3-table-wrap">
        <table className="core-v3-table">
          <thead>
            <tr>
              <th>字段</th>
              <th>候选值</th>
              <th>来源族</th>
              <th>状态</th>
              <th>置信</th>
              <th>依据</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.field_key} className={`matrix-${row.status.toLowerCase()}`}>
                <td>{row.label}</td>
                <td><code>{row.candidate_value || "待补充"}</code></td>
                <td>{row.supporting_sources.length ? row.supporting_sources.join(" / ") : "-"}</td>
                <td><span className={`core-v3-chip status-${row.status.toLowerCase()}`}>{coreV3StatusLabel(row.status)}</span></td>
                <td>{row.confidence.toFixed(2)}</td>
                <td>{row.rationale}</td>
              </tr>
            ))}
            {!sorted.length ? (
              <tr><td colSpan={6} className="empty">暂无交叉验证矩阵。</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </article>
  );
}
