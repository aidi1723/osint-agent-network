import type { GraphNode, GraphEdge } from "./graph";

export type { GraphNode, GraphEdge };

export type Tool = {
  name: string;
  display_name: string;
  execution_mode: string;
  accepts: string[];
  produces: string[];
  requires_credentials: boolean;
  enabled_by_default: boolean;
};

export type TradePartner = {
  name: string;
  country: string;
  trade_count: number;
  products: string[];
  first_trade: string;
  last_trade: string;
};

export type SupplyChainData = {
  company: string;
  downstream: {
    customers: TradePartner[];
    total_count: number;
  };
  upstream: {
    suppliers: TradePartner[];
    total_count: number;
  };
};

export type IntelligenceData = {
  investigation_id: string;
  contacts: {
    emails: Array<{
      value: string;
      source: string;
      confidence: number;
      verified: boolean;
      context: string;
    }>;
    phones: Array<{
      value: string;
      source: string;
      confidence: number;
      verified: boolean;
      context: string;
    }>;
    social: Array<{
      type: string;
      value: string;
      source: string;
      confidence: number;
      context: string;
    }>;
    websites: string[];
    summary: {
      total: number;
      emails_count: number;
      phones_count: number;
      social_count: number;
      websites_count: number;
    };
  };
  social: {
    profiles: Array<{
      platform: string;
      username: string;
      url: string;
      display_name?: string;
      bio?: string;
      location?: string;
      followers?: number;
      verified: boolean;
      avatar_url?: string;
      external_links: string[];
      source: string;
      confidence: number;
    }>;
    platforms: string[];
    summary: {
      total: number;
      professional: number;
      personal: number;
      public: number;
    };
  };
  products: {
    products: Array<{
      name: string;
      category?: string;
      hs_code?: string;
      description?: string;
      source: string;
      mention_count: number;
      confidence: number;
      contexts: string[];
    }>;
    categories: string[];
    hs_codes: string[];
    main_products: Array<{
      name: string;
      category?: string;
      mention_count: number;
      confidence: number;
    }>;
    summary: {
      total_products: number;
      categories_count: number;
      hs_codes_count: number;
      main_products_count: number;
    };
  };
};

export type Investigation = {
  id: string;
  name: string;
  seed_type: string;
  seed_value: string;
  strategy: string;
  status: string;
  created_at: string;
  updated_at?: string | null;
  claimed_by_agent_name: string | null;
  summary: string;
  report_markdown: string;
  confidence: number | null;
  max_depth: number;
  max_jobs: number;
  max_entities: number;
  metadata?: Record<string, unknown>;
  entities?: Entity[];
  evidence?: EvidenceItem[];
  evidence_ledger?: EvidenceLedgerRecord[];
  facts?: FactRecord[];
  hypotheses?: HypothesisRecord[];
  hypothesis_analysis?: HypothesisAnalysis;
  relationships?: Relationship[];
  jobs?: Job[];
  job_counts?: Record<string, number>;
  risk_report?: RiskReport;
  intelligence_memory?: IntelligenceMemory;
  quality_assessment?: QualityAssessment;
  intelligence_requirements?: IntelligenceRequirements;
  cross_verification_matrix?: CrossVerificationRow[];
  graph?: InvestigationGraph;
  decision_profile?: Investigation;
  combined_graph?: InvestigationGraph;
};

export type Agent = {
  id: string;
  agent_name: string;
  agent_type: string;
  capabilities: string[];
  status: string;
  last_seen_at: string;
};

export type Entity = {
  id: string;
  type: string;
  value: string;
  source_tool: string;
  confidence: number;
};

export type EvidenceItem = {
  id: string;
  entity_value: string;
  evidence_kind: string;
  source_tool: string;
  snippet: string;
};

export type EvidenceLedgerRecord = {
  id: string;
  investigation_id: string;
  source_url: string;
  source_type: string;
  source_tool: string;
  snippet: string;
  observed_at: string;
  admiralty_code: string;
  source_reliability: string;
  information_credibility: string;
  content_hash: string;
};

export type FactRecord = {
  id: string;
  investigation_id: string;
  statement: string;
  subject: string;
  predicate: string;
  object: string;
  status: string;
  promotion_stage?: string;
  confidence: number;
  admiralty_code: string;
  evidence_ids: string[];
  observed_at: string;
  valid_from: string;
  valid_to?: string | null;
  supersedes_fact_id?: string | null;
};

export type IntelligencePir = {
  id: string;
  question: string;
  priority: string;
  status: string;
  answer: string;
  confidence: number;
  linked_fact_ids: string[];
  remaining_gaps: string[];
};

export type IntelligenceEei = {
  id: string;
  label: string;
  field_key: string;
  required: boolean;
  status: string;
  linked_entity_values: string[];
  linked_fact_ids: string[];
};

export type IntelligenceRequirements = {
  decision_context: string;
  confidence_requirement: string;
  pirs: IntelligencePir[];
  eeis: IntelligenceEei[];
};

export type CrossVerificationRow = {
  field_key: string;
  label: string;
  candidate_value: string;
  supporting_sources: string[];
  contradicting_sources: string[];
  source_count: number;
  independent_source_count: number;
  best_admiralty_code?: string;
  status: string;
  confidence: number;
  linked_evidence_ids: string[];
  linked_fact_ids: string[];
  rationale: string;
};

export type HypothesisRecord = {
  id: string;
  investigation_id: string;
  statement: string;
  mutually_exclusive_group: string;
  status: string;
  support_score: number;
  inconsistency_score: number;
  supporting_evidence: string[];
  contradictory_evidence: string[];
  created_at: string;
  updated_at: string;
};

export type HypothesisAnalysis = {
  most_likely_hypothesis: string;
  triggered_indicators: string[];
  indicator_activation_rate: number;
  confidence_language: string;
  updated_at?: string;
};

export type Relationship = {
  id: string;
  from_value: string;
  to_value: string;
  relationship_type: string;
  confidence: number;
};

export type Job = {
  id: string;
  tool_name: string;
  target_type: string;
  target_value: string;
  depth: number;
  status: string;
  agent_role?: string;
  output_contract?: string;
  depends_on?: string;
  claimed_by_agent_id?: string | null;
  claimed_by_agent_name?: string | null;
  claimed_at?: string | null;
  heartbeat_at?: string | null;
  attempt_count?: number;
  last_error?: string;
};

export type RiskSignal = {
  kind: string;
  severity: string;
  summary: string;
  evidence_values: string[];
};

export type RiskReport = {
  overall_risk_score?: number;
  overall_risk_level?: string;
  category_scores?: Record<string, number>;
  review_required?: boolean;
  top_risk_signals?: RiskSignal[];
  public_profile_summary?: Record<string, string[]>;
};

export type IntelligenceMemoryFinding = {
  type: string;
  value: string;
  source_tool: string;
  confidence: number;
  evidence_count?: number;
};

export type IntelligenceMemoryGap = {
  key: string;
  label: string;
  reason: string;
  related_jobs?: string[];
};

export type DirectedCollectionItem = {
  gap_key: string;
  agent_focus: string;
  prompt: string;
  related_jobs?: string[];
};

export type IntelligenceMemory = {
  coverage: {
    confirmed_entities: number;
    review_items: number;
    collection_gaps: number;
    evidence_items: number;
    relationships: number;
  };
  confirmed_findings: IntelligenceMemoryFinding[];
  review_findings: Array<Record<string, unknown>>;
  collection_gaps: IntelligenceMemoryGap[];
  directed_collection: DirectedCollectionItem[];
};

export type QualityCheck = {
  key: string;
  label: string;
  present: boolean;
  weight: number;
  score: number;
  reason: string;
};

export type QualityAssessment = {
  score: number;
  completion_ready: boolean;
  minimum_score: number;
  missing_keys: string[];
  blocking_keys: string[];
  checks: QualityCheck[];
};

export type InvestigationGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  summary: {
    nodes: number;
    edges: number;
    risk_nodes: number;
    evidence_nodes: number;
    evidence_ledger_nodes?: number;
    fact_nodes?: number;
    hypothesis_nodes?: number;
    source_nodes?: number;
    osint_signal_nodes?: number;
    memory_findings?: number;
    collection_gaps?: number;
  };
};

export type DataMetric = {
  label: string;
  value: string | number;
};

export type SystemScriptStatus = {
  path: string;
  present: boolean;
  executable: boolean;
};

export type SystemStatus = {
  service: string;
  status: string;
  database: {
    status: string;
    path: string;
    exists: boolean;
    size_bytes: number;
    schema_version_count: number;
    latest_schema_version: string;
    error?: string;
  };
  schema_versions: Array<{ version: string; applied_at: string }>;
  investigations: {
    total: number;
    by_status: Record<string, number>;
  };
  jobs: {
    total: number;
    by_status: Record<string, number>;
  };
  records: {
    entities: number;
    evidence: number;
    evidence_ledger: number;
    facts: number;
  };
  tools: {
    registered: number;
    enabled_by_default: number;
    health?: {
      total: number;
      ready: number;
      missing_config: number;
      missing_executable: number;
      credential_blocked: number;
      disabled: number;
      runnable: number;
      attention_required: number;
    };
  };
  scripts: {
    backup: SystemScriptStatus;
    healthcheck: SystemScriptStatus;
    verify: SystemScriptStatus;
  };
};
