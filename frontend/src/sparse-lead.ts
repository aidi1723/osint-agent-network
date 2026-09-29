export type SparseLeadForm = {
  platform: string;
  lead_display_name: string;
  member_id: string;
  country_region: string;
  registration_year: string;
  company_name_raw: string;
  privacy_state: string;
  categoriesText: string;
  recentRfqsText: string;
  operator_notes: string;
};

export type SparseLeadMetadata = {
  platform: string;
  lead_display_name: string;
  member_id: string;
  country_region: string;
  registration_year: string;
  company_name_raw: string;
  privacy_state: string;
  categories: string[];
  recent_rfqs: string[];
  operator_notes: string;
};

export const defaultSparseLeadForm: SparseLeadForm = {
  platform: "Alibaba",
  lead_display_name: "",
  member_id: "",
  country_region: "",
  registration_year: "",
  company_name_raw: "",
  privacy_state: "email_phone_hidden",
  categoriesText: "",
  recentRfqsText: "",
  operator_notes: "",
};

export function parseLines(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function buildSparseLeadMetadata(form: SparseLeadForm): SparseLeadMetadata {
  return {
    platform: form.platform.trim(),
    lead_display_name: form.lead_display_name.trim(),
    member_id: form.member_id.trim(),
    country_region: form.country_region.trim(),
    registration_year: form.registration_year.trim(),
    company_name_raw: form.company_name_raw.trim(),
    privacy_state: form.privacy_state.trim(),
    categories: parseLines(form.categoriesText),
    recent_rfqs: parseLines(form.recentRfqsText),
    operator_notes: form.operator_notes.trim(),
  };
}

export function sparseLeadSeedValue(metadata: SparseLeadMetadata) {
  const displayName = metadata.lead_display_name || metadata.company_name_raw || "未命名弱线索";
  return metadata.member_id ? `${displayName} / ${metadata.member_id}` : displayName;
}

type StageJob = {
  tool_name: string;
  status: string;
};

export function sparseLeadStages(jobs: StageJob[]) {
  const byTool = new Map(jobs.map((job) => [job.tool_name, job.status]));
  return [
    { key: "anchors", label: "锚点提取", status: byTool.get("lead_anchor_extraction") ?? "QUEUED" },
    { key: "queries", label: "约束检索", status: byTool.get("constrained_query_planning") ?? "QUEUED" },
    { key: "candidates", label: "候选发现", status: byTool.get("candidate_business_discovery") ?? "QUEUED" },
    { key: "identity", label: "身份匹配", status: byTool.get("identity_match_review") ?? "QUEUED" },
    { key: "ach", label: "ACH 判断", status: byTool.get("analysis_judgement") ?? "QUEUED" },
    { key: "bluf", label: "BLUF 报告", status: byTool.get("analysis_judgement") ?? "QUEUED" },
    { key: "collection", label: "定向采集", status: byTool.get("analysis_judgement") ?? "QUEUED" },
  ];
}

export function isSparseLeadInvestigation(seedType: string) {
  return seedType === "sparse_lead";
}
