import type { CrossVerificationRow, FactRecord } from "./types";

export const promotionStageOrder = [
  "RAW_OBSERVATION",
  "CANDIDATE_FACT",
  "ASSESSED_FACT",
  "ACCEPTED_FACT",
  "REJECTED_FACT",
] as const;

const labels: Record<string, string> = {
  RAW_OBSERVATION: "原始观察",
  CANDIDATE_FACT: "候选事实",
  ASSESSED_FACT: "已评估事实",
  ACCEPTED_FACT: "已采纳事实",
  REJECTED_FACT: "已拒绝事实",
  MISSING: "缺失",
  CANDIDATE: "候选",
  SUPPORTED: "有来源支持",
  LIKELY: "较可信",
  CONFIRMED: "已确认",
  CONFLICTED: "存在冲突",
  NEEDS_REVIEW: "需复核",
  OPEN: "待回答",
  PARTIAL: "部分回答",
  ANSWERED: "已回答",
  BLOCKED: "受阻",
};

const fieldPriority: Record<string, number> = {
  company_identity: 1,
  official_website: 2,
  contact_email: 3,
  contact_phone: 4,
  operation_location: 5,
  registration: 6,
  business_scope: 7,
  decision_maker: 8,
  purchase_intent: 9,
  risk_signal: 10,
};

const severity: Record<string, number> = {
  CONFLICTED: 0,
  NEEDS_REVIEW: 1,
  MISSING: 2,
  CANDIDATE: 3,
  SUPPORTED: 4,
  LIKELY: 5,
  CONFIRMED: 6,
};

export function coreV3StatusLabel(status?: string) {
  return labels[status ?? ""] ?? status ?? "未知";
}

export function sortMatrixRows(rows: CrossVerificationRow[] = []) {
  return [...rows].sort((a, b) => {
    const byPriority = (fieldPriority[a.field_key] ?? 99) - (fieldPriority[b.field_key] ?? 99);
    if (byPriority !== 0) return byPriority;
    return (severity[a.status] ?? 99) - (severity[b.status] ?? 99);
  });
}

export function factPromotionCounts(facts: Partial<FactRecord>[] = []) {
  const counts = {
    RAW_OBSERVATION: 0,
    CANDIDATE_FACT: 0,
    ASSESSED_FACT: 0,
    ACCEPTED_FACT: 0,
    REJECTED_FACT: 0,
  };
  for (const fact of facts) {
    const stage = fact.promotion_stage ?? "CANDIDATE_FACT";
    if (stage in counts) counts[stage as keyof typeof counts] += 1;
  }
  return counts;
}
