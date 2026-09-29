import type { EvidenceLedgerRecord, FactRecord, HypothesisAnalysis, HypothesisRecord, IntelligenceMemory } from "./types";

export type CoreV2Coverage = {
  facts: number;
  confirmedFacts: number;
  contacts: number;
  evidenceLedger: number;
  hypotheses: number;
  gaps: number;
};

export type ReportAuditItem = {
  key: string;
  label: string;
  status: "ok" | "missing" | "review";
  count: number;
  detail: string;
};

const CONTACT_PREDICATE_TOKENS = ["email", "phone", "telephone", "contact", "whatsapp", "wechat"];

export function factStatusLabel(status: string) {
  const labels: Record<string, string> = {
    CONFIRMED: "已确认",
    LIKELY: "较可能",
    CONTRADICTED: "被反证",
    RETIRED: "已过期",
    NEEDS_REVIEW: "待复核",
  };
  return labels[status] ?? status;
}

export function hypothesisStatusLabel(status: string) {
  const labels: Record<string, string> = {
    MOST_LIKELY: "当前最难证伪",
    PLAUSIBLE: "可成立",
    DISFAVORED: "较弱",
    REJECTED: "已排除",
    UNVERIFIED: "未验证",
  };
  return labels[status] ?? status;
}

export function contactFacts(facts: FactRecord[]) {
  return facts.filter((fact) => {
    const predicate = fact.predicate.toLowerCase();
    const statement = fact.statement.toLowerCase();
    return CONTACT_PREDICATE_TOKENS.some((token) => predicate.includes(token) || statement.includes(token));
  });
}

export function coreV2Coverage(
  facts: FactRecord[],
  evidenceLedger: EvidenceLedgerRecord[],
  hypotheses: HypothesisRecord[],
  memory?: IntelligenceMemory,
): CoreV2Coverage {
  const contacts = contactFacts(facts);
  return {
    facts: facts.length,
    confirmedFacts: facts.filter((fact) => ["CONFIRMED", "LIKELY"].includes(fact.status)).length,
    contacts: contacts.length,
    evidenceLedger: evidenceLedger.length,
    hypotheses: hypotheses.length,
    gaps: memory?.collection_gaps?.length ?? 0,
  };
}

export function reportAuditItems(params: {
  facts: FactRecord[];
  evidenceLedger: EvidenceLedgerRecord[];
  hypotheses: HypothesisRecord[];
  analysis?: HypothesisAnalysis;
  memory?: IntelligenceMemory;
  reportMarkdown?: string;
}): ReportAuditItem[] {
  const facts = params.facts;
  const evidenceLedger = params.evidenceLedger;
  const hypotheses = params.hypotheses;
  const contacts = contactFacts(facts);
  const report = params.reportMarkdown ?? "";
  const gaps = params.memory?.collection_gaps ?? [];
  return [
    {
      key: "confirmed_facts",
      label: "确认事实",
      status: facts.some((fact) => ["CONFIRMED", "LIKELY"].includes(fact.status)) ? "ok" : "missing",
      count: facts.length,
      detail: "已确认的主营业务、主体、分支、联系方式等应进入事实池和报告底座。",
    },
    {
      key: "contacts",
      label: "联系人/联系方式",
      status: contacts.length ? "ok" : "missing",
      count: contacts.length,
      detail: "电话、邮箱、联系人、联系页等重要触达信息必须在报告中可追溯。",
    },
    {
      key: "evidence_ledger",
      label: "证据账本",
      status: evidenceLedger.length ? "ok" : "missing",
      count: evidenceLedger.length,
      detail: "每条确认信息至少需要可回看来源、Admiralty Code 和摘要片段。",
    },
    {
      key: "ach",
      label: "ACH 假说",
      status: params.analysis?.most_likely_hypothesis || hypotheses.length >= 2 ? "ok" : "review",
      count: hypotheses.length,
      detail: "模糊结论应保留竞争性假说和当前最难证伪解释。",
    },
    {
      key: "directed_collection",
      label: "下一步采集",
      status: gaps.length ? "review" : "ok",
      count: gaps.length,
      detail: gaps.length ? "仍存在情报缺口，应作为下一轮 agent 采集基础。" : "当前系统未识别新的结构化采集缺口。",
    },
    {
      key: "bottom_report",
      label: "底部报告",
      status: report.trim().length ? "ok" : "review",
      count: report.trim().length ? 1 : 0,
      detail: "即使不进入槽位，事实池、缺口、联系人和证据也要能被报告层承载。",
    },
  ];
}
