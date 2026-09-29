import assert from "node:assert/strict";

import { chooseDefaultInvestigation } from "../src/default-investigation.ts";
import type { Investigation } from "../src/types.ts";

function investigation(overrides: Partial<Investigation>): Investigation {
  return {
    id: "base",
    name: "base",
    seed_type: "company",
    seed_value: "base",
    strategy: "deep",
    status: "NEEDS_REVIEW",
    created_at: "2026-05-20T00:00:00+00:00",
    updated_at: "2026-05-20T00:00:00+00:00",
    claimed_by_agent_name: null,
    summary: "base summary",
    report_markdown: "",
    confidence: 0.5,
    max_depth: 2,
    max_jobs: 10,
    max_entities: 100,
    ...overrides,
  };
}

const olderReviewed = investigation({
  id: "old-review",
  name: "旧的待复核任务",
  updated_at: "2026-05-20T11:03:18+00:00",
  summary: "old result",
});

const latestReviewed = investigation({
  id: "latest-review",
  name: "新的 OLGLASS 认可任务",
  updated_at: "2026-05-21T13:30:09+00:00",
  summary: "OLGLASS INTERNACIONAL S.A.S.",
});

const newestEmpty = investigation({
  id: "newest-empty",
  name: "最新但无可展示内容",
  updated_at: "2026-05-21T14:00:00+00:00",
  summary: "",
  report_markdown: "",
  confidence: null,
});

assert.equal(
  chooseDefaultInvestigation([olderReviewed, latestReviewed, newestEmpty])?.id,
  "latest-review",
  "default investigation should prefer the latest review-ready investigation with reportable content",
);

console.log("default investigation checks passed");
