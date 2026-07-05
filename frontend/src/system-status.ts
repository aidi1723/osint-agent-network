import type { DataMetric, SystemStatus } from "./types";

export function systemStatusTone(status?: SystemStatus | null): "ok" | "warn" | "down" {
  if (!status) return "warn";
  if (status.status !== "ok") return "down";
  if (status.database?.status !== "ok") return "down";
  if (!status.scripts?.backup?.present || !status.scripts?.healthcheck?.present) return "warn";
  if ((status.tools?.health?.attention_required ?? 0) > 0) return "warn";
  return "ok";
}

export function systemStatusMetrics(status?: SystemStatus | null): DataMetric[] {
  return [
    { label: "数据库", value: formatBytes(status?.database?.size_bytes ?? 0) },
    { label: "Schema", value: status?.database?.schema_version_count ?? 0 },
    { label: "任务", value: status?.investigations?.total ?? 0 },
    { label: "队列", value: status?.jobs?.total ?? 0 },
    { label: "工具", value: `${status?.tools?.health?.ready ?? status?.tools?.enabled_by_default ?? 0}/${status?.tools?.registered ?? 0}` },
    { label: "备份", value: status?.scripts?.backup?.present ? "可用" : "缺失" },
  ];
}

export function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
