import React from "react";
import { BarChart3 } from "lucide-react";
import { DataRow } from "./DataRow";
import { labelOf, riskLevelLabels, riskCategoryLabels } from "../labels";
import type { RiskReport } from "../types";

export function RiskReviewPanel({ riskReport }: { riskReport: RiskReport }) {
  const hasScore = typeof riskReport.overall_risk_score === "number";
  const categoryScores = riskReport.category_scores ?? {};
  const signals = riskReport.top_risk_signals ?? [];
  const summary = riskReport.public_profile_summary ?? {};

  return (
    <article className="review-panel risk-panel">
      <div className="section-heading">
        <h3>风险复核</h3>
        <span>{hasScore ? labelOf(riskLevelLabels, riskReport.overall_risk_level ?? "low") : "未生成"}</span>
      </div>
      <div className="risk-score-row">
        <div className={`risk-score risk-${riskReport.overall_risk_level ?? "low"}`}>
          <BarChart3 size={18} />
          <strong>{hasScore ? riskReport.overall_risk_score : "-"}</strong>
          <span>总分</span>
        </div>
        <div className="category-grid">
          {Object.entries(categoryScores).map(([key, value]) => (
            <div key={key} className="category-score">
              <span>{labelOf(riskCategoryLabels, key)}</span>
              <strong>{value}</strong>
            </div>
          ))}
          {!Object.keys(categoryScores).length ? (
            <span className="muted">运行社媒相关任务后生成分类分。</span>
          ) : null}
        </div>
      </div>
      <div className="detail-stack compact-stack">
        {signals.map((signal, index) => (
          <DataRow
            key={`${signal.kind}-${index}`}
            title={`${signal.kind} / ${signal.severity}`}
            meta="需要人工复核"
            body={signal.summary}
          />
        ))}
        {!signals.length ? <div className="empty compact">暂无风险信号。</div> : null}
      </div>
      <div className="profile-summary">
        {Object.entries(summary).map(([key, values]) =>
          values?.length ? (
            <div key={key}>
              <span>{key}</span>
              <code>{values.slice(0, 2).join("、")}</code>
            </div>
          ) : null,
        )}
      </div>
    </article>
  );
}
