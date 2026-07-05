import { CheckCircle2, CircleAlert, CircleHelp } from "lucide-react";
import { coreV2Coverage, reportAuditItems, type ReportAuditItem } from "../core-v2";
import type { EvidenceLedgerRecord, FactRecord, HypothesisAnalysis, HypothesisRecord, IntelligenceMemory } from "../types";

type ReportAuditPanelProps = {
  facts?: FactRecord[];
  evidenceLedger?: EvidenceLedgerRecord[];
  hypotheses?: HypothesisRecord[];
  analysis?: HypothesisAnalysis;
  memory?: IntelligenceMemory;
  reportMarkdown?: string;
};

export function ReportAuditPanel({
  facts = [],
  evidenceLedger = [],
  hypotheses = [],
  analysis,
  memory,
  reportMarkdown = "",
}: ReportAuditPanelProps) {
  const coverage = coreV2Coverage(facts, evidenceLedger, hypotheses, memory);
  const items = reportAuditItems({ facts, evidenceLedger, hypotheses, analysis, memory, reportMarkdown });
  return (
    <article className="core-v2-panel report-audit-panel">
      <div className="section-heading">
        <h3>报告审计与接力基础</h3>
        <span>{coverage.confirmedFacts} 个确认事实 / {coverage.gaps} 个缺口</span>
      </div>
      <div className="memory-stat-grid core-v2-stat-grid">
        <span>事实 {coverage.facts}</span>
        <span>联系方式 {coverage.contacts}</span>
        <span>证据账本 {coverage.evidenceLedger}</span>
        <span>假说 {coverage.hypotheses}</span>
      </div>
      <div className="audit-list">
        {items.map((item) => (
          <AuditRow key={item.key} item={item} />
        ))}
      </div>
    </article>
  );
}

function AuditRow({ item }: { item: ReportAuditItem }) {
  const Icon = item.status === "ok" ? CheckCircle2 : item.status === "missing" ? CircleAlert : CircleHelp;
  return (
    <div className={`audit-row audit-${item.status}`}>
      <Icon size={15} />
      <strong>{item.label}</strong>
      <span>{item.count}</span>
      <p>{item.detail}</p>
    </div>
  );
}
