import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react";
import type { IntelligenceMemory, Job, QualityAssessment } from "../types";
import { labelOf, agentRoleLabels, jobStateLabels } from "../labels";

type QualityGatePanelProps = {
  assessment?: QualityAssessment;
  memory?: IntelligenceMemory;
  jobs?: Job[];
};

export function QualityGatePanel({ assessment, memory, jobs = [] }: QualityGatePanelProps) {
  const waitingJobs = jobs.filter((job) => ["WAITING_AGENT", "CLAIMED", "RUNNING", "BLOCKED", "FAILED", "PARTIAL_FAILED"].includes(job.status));
  const gaps = memory?.directed_collection ?? [];
  const score = assessment?.score ?? 0;
  const ready = Boolean(assessment?.completion_ready);
  const missing = assessment?.checks.filter((item) => !item.present).slice(0, 6) ?? [];

  return (
    <article className={`core-v2-panel quality-gate-panel${ready ? " quality-ready" : " quality-review"}`}>
      <div className="section-heading">
        <h3>质量闸门 / 下一步</h3>
        <span>{score} / 100</span>
      </div>
      <div className="quality-score-row">
        <div className="quality-score">
          {ready ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
          <strong>{ready ? "可完成" : "需复核"}</strong>
          <span>最低 {assessment?.minimum_score ?? 72} 分</span>
        </div>
        <div className="quality-check-grid">
          {(assessment?.checks ?? []).slice(0, 12).map((item) => (
            <span key={item.key} className={item.present ? "quality-check-ok" : "quality-check-missing"}>
              {item.present ? <CheckCircle2 size={13} /> : <CircleDashed size={13} />}
              {item.label}
            </span>
          ))}
        </div>
      </div>
      {missing.length ? (
        <div className="quality-gap-list">
          {missing.map((item) => (
            <span key={item.key}>{item.reason}</span>
          ))}
        </div>
      ) : null}
      <div className="quality-next-grid">
        <div>
          <strong>接力动作</strong>
          {(gaps.length ? gaps.slice(0, 3) : [{ agent_focus: "继续采集", prompt: "补齐证据账本、事实池和 BLUF 后再完成任务。" }]).map((item) => (
            <p key={`${item.agent_focus}-${item.prompt}`}>{item.agent_focus}：{item.prompt}</p>
          ))}
        </div>
        <div>
          <strong>等待/异常任务</strong>
          {waitingJobs.slice(0, 4).map((job) => (
            <p key={job.id}>
              {job.tool_name}：{labelOf(jobStateLabels, job.status)} / {labelOf(agentRoleLabels, job.agent_role ?? "tool_agent")}
            </p>
          ))}
          {!waitingJobs.length ? <p>暂无阻塞或等待 Agent 的任务。</p> : null}
        </div>
      </div>
    </article>
  );
}
