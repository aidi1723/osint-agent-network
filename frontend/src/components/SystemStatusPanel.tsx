import { systemStatusMetrics, systemStatusTone } from "../system-status";
import type { SystemStatus } from "../types";
import { MiniMetrics } from "./Metric";

export function SystemStatusPanel({ status }: { status?: SystemStatus | null }) {
  const tone = systemStatusTone(status);
  const latest = status?.database?.latest_schema_version || "未记录";
  const toolHealth = status?.tools?.health;
  return (
    <section className={`panel system-status-panel system-status-${tone}`}>
      <div className="panel-heading">
        <h2>系统自检</h2>
        <span>{tone === "ok" ? "稳定" : tone === "warn" ? "需关注" : "异常"}</span>
      </div>
      <MiniMetrics metrics={systemStatusMetrics(status)} />
      <div className="system-status-grid">
        <div>
          <strong>数据库</strong>
          <span>{status?.database?.status ?? "unknown"} / {latest}</span>
        </div>
        <div>
          <strong>脚本</strong>
          <span>backup {status?.scripts?.backup?.present ? "ok" : "missing"} · healthcheck {status?.scripts?.healthcheck?.present ? "ok" : "missing"}</span>
        </div>
        <div>
          <strong>工具健康</strong>
          <span>ready {toolHealth?.ready ?? 0} · attention {toolHealth?.attention_required ?? 0}</span>
        </div>
        <div>
          <strong>阻塞类型</strong>
          <span>config {toolHealth?.missing_config ?? 0} · exec {toolHealth?.missing_executable ?? 0} · cred {toolHealth?.credential_blocked ?? 0}</span>
        </div>
      </div>
    </section>
  );
}
