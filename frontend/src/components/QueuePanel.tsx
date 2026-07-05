import React from "react";
import { Play } from "lucide-react";
import { DataRow } from "./DataRow";
import { labelOf, agentRoleLabels, targetTypeLabels, jobStateLabels } from "../labels";
import type { Job } from "../types";

interface QueuePanelProps {
  jobCounts: Record<string, number>;
  jobs: Job[];
  running: boolean;
  onRun: () => void;
}

function queueHint(job: Job) {
  if (job.tool_name === "spiderfoot" && job.status === "BLOCKED") {
    return "SpiderFoot 需要 SPIDERFOOT_BASE_URL；当前任务保持可追溯阻塞状态。";
  }
  if (job.status === "BLOCKED") {
    return "工具缺命令或缺配置，等待环境补齐后重跑。";
  }
  if (["amass", "spiderfoot", "sherlock"].includes(job.tool_name) && job.status === "COMPLETED") {
    return "工具已回写，结果默认作为候选证据进入交叉验证。";
  }
  if (["amass", "spiderfoot", "sherlock"].includes(job.tool_name) && job.status === "PARTIAL_FAILED") {
    return "工具部分失败，保留已有 artifact 与事件摘要供复核。";
  }
  return "";
}

export function QueuePanel({ jobCounts, jobs, running, onRun }: QueuePanelProps) {
  const queued = jobCounts.QUEUED ?? 0;
  const waiting = (jobCounts.WAITING_AGENT ?? 0) + (jobCounts.CLAIMED ?? 0);
  const blocked = jobCounts.BLOCKED ?? 0;
  const visibleRoles = Array.from(new Set(jobs.map((job) => job.agent_role ?? "tool_agent")));
  const queueStatusHint =
    queued > 0
      ? "队列中仍有可执行任务。"
      : waiting > 0
        ? "当前等待外部 Agent 或已被认领；如长时间无心跳，可在任务池释放过期认领。"
        : blocked > 0
          ? "当前任务被工具命令或配置阻塞；补齐环境后可重试任务。"
          : "当前没有待执行队列。";

  return (
    <article className="review-panel">
      <div className="section-heading">
        <h3>执行队列</h3>
        <button type="button" onClick={onRun} disabled={running || queued === 0}>
          <Play size={16} />
          {running ? "运行中" : "运行队列"}
        </button>
      </div>
      <div className="job-strip">
        {["QUEUED", "WAITING_AGENT", "CLAIMED", "RUNNING", "COMPLETED", "PARTIAL_FAILED", "FAILED", "BLOCKED"].map((s) => (
          <span key={s} className={`job-chip job-${s.toLowerCase()}`}>
            {labelOf(jobStateLabels, s)} {jobCounts[s] ?? 0}
          </span>
        ))}
      </div>
      <p className="queue-status-hint">{queueStatusHint}</p>
      {visibleRoles.length ? (
        <div className="job-role-strip">
          {visibleRoles.map((role) => (
            <span key={role}>{labelOf(agentRoleLabels, role)}</span>
          ))}
        </div>
      ) : null}
      <div className="detail-stack compact-stack">
        {jobs.slice(0, 4).map((job) => (
          <DataRow
            key={job.id}
            title={`${job.tool_name} / ${labelOf(targetTypeLabels, job.target_type)}:${job.target_value}`}
            meta={`${labelOf(agentRoleLabels, job.agent_role ?? "tool_agent")} / ${labelOf(jobStateLabels, job.status)} / depth ${job.depth}${job.claimed_by_agent_name ? ` / ${job.claimed_by_agent_name}` : ""}`}
            body={[
              job.output_contract ? `产出：${job.output_contract}${job.depends_on ? `；依赖：${job.depends_on}` : ""}` : "",
              queueHint(job),
            ].filter(Boolean).join("；")}
          />
        ))}
        {jobs.length > 4 ? (
          <details className="compact-details">
            <summary>展开其余队列 {jobs.length - 4} 条</summary>
            {jobs.slice(4).map((job) => (
              <DataRow
                key={job.id}
                title={`${job.tool_name} / ${labelOf(targetTypeLabels, job.target_type)}:${job.target_value}`}
            meta={`${labelOf(agentRoleLabels, job.agent_role ?? "tool_agent")} / ${labelOf(jobStateLabels, job.status)} / depth ${job.depth}${job.claimed_by_agent_name ? ` / ${job.claimed_by_agent_name}` : ""}`}
                body={[
                  job.output_contract ? `产出：${job.output_contract}${job.depends_on ? `；依赖：${job.depends_on}` : ""}` : "",
                  queueHint(job),
                ].filter(Boolean).join("；")}
              />
            ))}
          </details>
        ) : null}
        {!jobs.length ? <div className="empty compact">暂无队列任务。</div> : null}
      </div>
    </article>
  );
}
