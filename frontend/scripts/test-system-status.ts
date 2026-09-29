import assert from "node:assert/strict";
import type { SystemStatus } from "../src/types.ts";
import { systemStatusMetrics, systemStatusTone } from "../src/system-status.ts";

const payload: SystemStatus = {
  service: "osint-agent-network",
  status: "ok",
  database: {
    status: "ok",
    path: "data/osint.sqlite",
    exists: true,
    schema_version_count: 2,
    latest_schema_version: "0002",
    size_bytes: 2048,
  },
  schema_versions: [{ version: "0002", applied_at: "2026-07-04T00:00:00Z" }],
  investigations: { total: 3, by_status: { OPEN: 1, NEEDS_REVIEW: 2 } },
  jobs: { total: 9, by_status: { QUEUED: 4 } },
  records: { entities: 10, evidence: 8, evidence_ledger: 6, facts: 4 },
  tools: {
    registered: 8,
    enabled_by_default: 6,
    health: {
      total: 8,
      ready: 6,
      missing_config: 1,
      missing_executable: 1,
      credential_blocked: 0,
      disabled: 0,
      runnable: 6,
      attention_required: 0,
    },
  },
  scripts: {
    backup: { path: "scripts/backup.sh", present: true, executable: true },
    healthcheck: { path: "scripts/healthcheck.sh", present: true, executable: true },
    verify: { path: "scripts/verify.sh", present: true, executable: true },
  },
};

assert.equal(systemStatusTone(payload), "ok");
assert.deepEqual(
  systemStatusMetrics(payload).map((item) => item.label),
  ["数据库", "Schema", "任务", "队列", "工具", "备份"],
);
assert.equal(systemStatusMetrics(payload)[0].value, "2.0 KB");
assert.equal(systemStatusMetrics(payload)[4].value, "6/8");

const degradedTools = {
  ...payload,
  tools: {
    ...payload.tools,
    health: {
      ...payload.tools.health!,
      ready: 4,
      attention_required: 2,
    },
  },
};

assert.equal(systemStatusTone(degradedTools), "warn");

console.log("system status helper checks passed");
