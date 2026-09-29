export const targetTypeLabels: Record<string, string> = {
  domain: "域名",
  email: "邮箱",
  username: "用户名",
  phone: "手机号",
  company: "企业",
  sparse_lead: "弱线索买家",
  organization: "组织",
};

export const agentRoleLabels: Record<string, string> = {
  tool_agent: "工具执行 Agent",
  lead_intake_agent: "线索录入 Agent",
  search_planning_agent: "检索规划 Agent",
  enterprise_intel_agent: "企业情报 Agent",
  social_intel_agent: "社媒情报 Agent",
  contact_discovery_agent: "联系方式 Agent",
  supply_chain_agent: "上下游 Agent",
  purchase_intent_agent: "采购意图 Agent",
  news_intel_agent: "企业动态 Agent",
  cross_verification_agent: "交叉验证 Agent",
  analysis_judgement_agent: "分析评价 Agent",
};

export const strategyLabels: Record<string, string> = {
  quick: "快速",
  standard: "标准",
  deep: "深度",
  maximum: "最大召回",
};

export const taskStateLabels: Record<string, string> = {
  OPEN: "开放认领",
  CLAIMED: "已认领",
  RUNNING: "运行中",
  NEEDS_REVIEW: "待复核",
  COMPLETED: "已完成",
  PARTIAL_FAILED: "部分失败",
  FAILED: "失败",
  CANCELLED: "已取消",
  STALE_CLAIM: "认领失效",
};

export const executionModeLabels: Record<string, string> = {
  sync_cli: "同步命令行",
  async_cli: "异步命令行",
  async_rest: "异步接口",
  sync_rest: "同步接口",
  resource_script: "资源脚本",
};

export const entityTypeLabels: Record<string, string> = {
  age_claim: "年龄声明",
  age_range: "年龄区间",
  bio_snippet: "公开简介",
  company_name_raw: "原始公司字段",
  country_region: "国家/地区",
  declared_location: "声明地区",
  dietary_preference: "饮食偏好",
  domain: "域名",
  email: "邮箱",
  external_link: "外部链接",
  gender_claim: "性别声明",
  hospitality_preference: "接待偏好",
  identity: "身份",
  interest_tag: "兴趣标签",
  likely_activity_region: "活动地区",
  news_article: "新闻报道",
  news_summary: "新闻摘要",
  news_title: "新闻标题",
  published_at: "发布时间",
  organization: "组织",
  phone: "电话",
  platform: "平台",
  platform_account: "平台账号",
  platform_member_id: "平台会员 ID",
  product_scope: "主营产品",
  production_base: "制造基地",
  market_coverage: "市场覆盖",
  address: "地址",
  business_scope: "主营业务",
  privacy_state: "隐私状态",
  profile_image_url: "公开头像",
  profile_url: "社媒主页",
  public_personal_attribute: "公开个人属性",
  purchase_category: "采购类目",
  registration_year: "注册年份",
  rfq_text: "RFQ 文本",
  social_profile: "社媒账号",
  username: "用户名",
};

export const evidenceKindLabels: Record<string, string> = {
  age_or_gender_public_record: "年龄/性别公开记录",
  business_email: "商务邮箱",
  candidate_public_record: "候选公开记录",
  commercial_decision_contact: "商业决策入口",
  identity_match_signal: "身份匹配信号",
  identity_mismatch_signal: "身份不匹配信号",
  official_contact: "官方联系方式",
  platform_profile_screenshot: "平台资料截图",
  company_news_report: "企业新闻报道",
  news_business_event: "企业动态线索",
  news_buying_signal: "新闻采购信号",
  news_risk_signal: "新闻风险信号",
  public_personal_attribute: "公开个人属性",
  public_profile_metadata: "公开主页资料",
  rfq_intent_signal: "RFQ 意图信号",
  rfq_noise_signal: "RFQ 噪声信号",
  role_confirmation: "角色确认",
  social_profile_exists: "社媒主页存在",
  third_party_business_profile: "第三方企业资料",
};

export const relationshipTypeLabels: Record<string, string> = {
  email_linked_to_social_profile: "邮箱关联社媒主页",
  legal_representative_and_manager: "法定代表/经理",
  official_company_phone: "官方公司电话",
  news_mentions_company: "新闻提及企业",
  news_supports_business_event: "新闻支持企业动态",
  news_supports_buying_signal: "新闻支持采购信号",
  news_supports_risk_signal: "新闻支持风险信号",
  person_has_public_age_range: "公开年龄区间",
  person_has_public_gender_claim: "公开性别声明",
  person_has_public_personal_attribute: "公开个人属性",
  possible_us_related_company_manager: "疑似美国关联公司负责人",
  profile_has_age_claim: "主页声明年龄",
  profile_has_bio_snippet: "主页简介",
  profile_has_declared_location: "主页声明地区",
  profile_has_external_link: "主页外链",
  profile_has_interest_tag: "主页兴趣标签",
  profile_has_likely_activity_region: "主页活动地区",
  profile_has_profile_image_url: "主页公开头像",
  sales_and_marketing_manager: "销售与市场负责人",
  uses_business_email: "使用商务邮箱",
  lead_has_platform_anchor: "线索包含平台锚点",
  username_has_social_profile: "用户名关联社媒主页",
  brand_associated_with_company: "品牌关联主体",
  brand_under_group: "品牌所属集团",
  official_website: "官方网站",
  regional_operation: "区域运营",
  official_company_address: "官方公司地址",
  brand_claims_production_base: "品牌声称制造基地",
  brand_claims_production_base_needs_review: "制造基地待复核",
  image_claim_needs_review: "图片声明待复核",
  third_party_links_brand: "第三方关联品牌",
};

export const graphNodeTypeLabels: Record<string, string> = {
  entity: "实体",
  evidence: "证据",
  evidence_ledger: "证据账本",
  fact: "事实",
  hypothesis: "假说",
  risk_signal: "风险信号",
  seed: "初始线索",
  source: "信息来源",
};

export const sourceKindLabels: Record<string, string> = {
  official_web: "官网",
  public_record: "公开登记",
  news: "新闻报道",
  social: "社媒",
  tool: "工具",
};

export const graphEdgeTypeLabels: Record<string, string> = {
  risk_attached_to_seed: "待复核",
  risk_supported_by: "风险依据",
  seed_matches_entity: "初始线索",
  source_emitted_entity: "信息来源",
  source_emitted_evidence: "信息来源",
  source_emitted_evidence_ledger: "信息来源",
  supports_entity: "证据支持",
  supports_relationship: "关系来源",
  subject_has_fact: "确认事实",
  fact_has_object: "事实对象",
  evidence_supports_fact: "证据支持事实",
  hypothesis_attached_to_seed: "分析假说",
  ...relationshipTypeLabels,
};

export const jobStateLabels: Record<string, string> = {
  QUEUED: "待执行",
  WAITING_AGENT: "等待 Agent",
  CLAIMED: "已认领",
  RUNNING: "运行中",
  COMPLETED: "完成",
  PARTIAL_FAILED: "部分失败",
  FAILED: "失败",
  BLOCKED: "阻塞",
  SKIPPED: "跳过",
};

export const riskLevelLabels: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

export const riskCategoryLabels: Record<string, string> = {
  identity_consistency: "身份一致性",
  contact_reputation: "联系方式风险",
  location_consistency: "地区一致性",
  business_content_risk: "业务内容风险",
  evidence_uncertainty: "证据不确定性",
};

export function labelOf(map: Record<string, string>, value: string) {
  return map[value] ?? value;
}

export function statusClass(status: string) {
  const map: Record<string, string> = {
    OPEN: "status status-open",
    CLAIMED: "status status-claimed",
    RUNNING: "status status-running",
    NEEDS_REVIEW: "status status-review",
    COMPLETED: "status status-completed",
    PARTIAL_FAILED: "status status-partial",
    FAILED: "status status-failed",
    CANCELLED: "status status-cancelled",
    STALE_CLAIM: "status status-stale",
    ARCHIVED: "status status-archived",
  };
  return map[status] ?? "status";
}
