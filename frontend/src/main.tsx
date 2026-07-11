import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, AlertTriangle, Cpu, Database, Filter, GitBranch, LogOut, Play, RefreshCcw, Search } from "lucide-react";
import { marked } from "marked";
import "./styles.css";
import { fetchJson, setUnauthorizedHandler } from "./api";
import { loadSession, login, logout, requestOptions } from "./auth";
import { combineGraphs, findDecisionProfileForInvestigation, visiblePrimaryInvestigations, type BundleInvestigation } from "./investigation-bundle";
import { labelOf, statusClass, targetTypeLabels, strategyLabels, taskStateLabels, agentRoleLabels, entityTypeLabels, evidenceKindLabels, relationshipTypeLabels } from "./labels";
import { Metric, MiniMetrics } from "./components/Metric";
import { DataRow } from "./components/DataRow";
import { TaskActions } from "./components/TaskActions";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { QueuePanel } from "./components/QueuePanel";
import { RiskReviewPanel } from "./components/RiskPanel";
import { HcsTemplateGraph } from "./components/HcsTemplateGraph";
import { MosaicEvidenceChain } from "./components/MosaicEvidenceChain";
import { IntelligenceMemoryPanel } from "./components/IntelligenceMemoryPanel";
import { HypothesisPanel } from "./components/HypothesisPanel";
import { ReportAuditPanel } from "./components/ReportAuditPanel";
import { QualityGatePanel } from "./components/QualityGatePanel";
import { IntelligenceRequirementsPanel } from "./components/IntelligenceRequirementsPanel";
import { CrossVerificationMatrixPanel } from "./components/CrossVerificationMatrixPanel";
import { FactPromotionPanel } from "./components/FactPromotionPanel";
import { SystemStatusPanel } from "./components/SystemStatusPanel";
import { SupplyChainPanel } from "./components/SupplyChainPanel";
import { IntelligencePanel } from "./components/IntelligencePanel";
import { AdminLogin } from "./components/AdminLogin";
import { buildCockpitMetrics, cockpitBluf } from "./dashboard-metrics";
import { chooseDefaultInvestigation } from "./default-investigation";
import { preferredDecisionLabel, preferredOrganizationLabel } from "./hcs-graph-data";
import { buildSparseLeadMetadata, defaultSparseLeadForm, isSparseLeadInvestigation, sparseLeadSeedValue, sparseLeadStages } from "./sparse-lead";
import { isActiveInvestigationStatus, isReviewableInvestigationStatus, sanitizeReportHtml, selectedTaskRowClassName } from "./ui-state";
import type { Tool, Investigation, Agent, DataMetric, SystemStatus } from "./types";

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";

type ConfirmState = {
  title: string;
  message: string;
  confirmLabel: string;
  danger: boolean;
  onConfirm: () => void;
} | null;

export function App() {
  const [checkingSession, setCheckingSession] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadSession(apiBase)
      .then((session) => {
        if (!active) return;
        const nextCsrfToken = authenticatedCsrfToken(session);
        if (session.authenticated && !nextCsrfToken) {
          throw new Error("authenticated session is missing csrf");
        }
        setAuthRequired(Boolean(session.required));
        setAuthenticated(Boolean(session.authenticated));
        setCsrfToken(nextCsrfToken);
      })
      .catch(() => {
        if (!active) return;
        setAuthRequired(true);
        setAuthenticated(false);
        setCsrfToken(null);
        setSessionError("无法确认登录状态，请验证凭据后重试。");
      })
      .finally(() => {
        if (active) setCheckingSession(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setAuthRequired(true);
      setAuthenticated(false);
      setCsrfToken(null);
      setSessionError("登录状态已失效，请重新验证。");
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  async function handleLogin(adminToken: string) {
    const session = await login(apiBase, adminToken);
    const nextCsrfToken = authenticatedCsrfToken(session);
    if (!session.authenticated || !nextCsrfToken) {
      throw new Error("authenticated login is missing csrf");
    }
    setAuthRequired(true);
    setAuthenticated(true);
    setCsrfToken(nextCsrfToken);
    setSessionError(null);
  }

  async function handleLogout() {
    if (!csrfToken) return;
    try {
      await logout(apiBase, csrfToken);
    } catch {
      // Local auth state must still be cleared when the session already expired.
    } finally {
      setAuthenticated(false);
      setCsrfToken(null);
      setSessionError(null);
    }
  }

  if (checkingSession) {
    return <main className="admin-login-shell"><div className="session-checking" role="status">正在验证登录状态...</div></main>;
  }
  if (authRequired && !authenticated) {
    return <AdminLogin onLogin={handleLogin} initialError={sessionError} />;
  }
  return (
    <OperationsConsole
      csrfToken={csrfToken}
      onLogout={authenticated && csrfToken ? handleLogout : undefined}
    />
  );
}

function authenticatedCsrfToken(session: {
  authenticated: boolean;
  csrf_token?: string;
}): string | null {
  if (!session.authenticated || typeof session.csrf_token !== "string") return null;
  return session.csrf_token.trim() ? session.csrf_token : null;
}

type OperationsConsoleProps = {
  csrfToken: string | null;
  onLogout?: () => Promise<void>;
};

function OperationsConsole({ csrfToken, onLogout }: OperationsConsoleProps) {
  const [tools, setTools] = useState<Tool[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [selected, setSelected] = useState<Investigation | null>(null);
  const [operationsOpen, setOperationsOpen] = useState(() => !selected);
  const [form, setForm] = useState({ name: "example.com 深度调查", seed_type: "domain", seed_value: "example.com", strategy: "deep" });
  const [requirementsForm, setRequirementsForm] = useState({
    decision_context: "qualify buyer or company lead",
    confidence_requirement: "standard",
  });
  const [sparseLeadForm, setSparseLeadForm] = useState(defaultSparseLeadForm);
  const [stateFilter, setStateFilter] = useState("active");
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runningJobs, setRunningJobs] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">("checking");
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const dataBoardRef = useRef<HTMLElement | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const createFormRef = useRef<HTMLFormElement | null>(null);

  function csrfHeaders(): Record<string, string> | undefined {
    return csrfToken ? { "X-CSRF-Token": csrfToken } : undefined;
  }

  async function refresh() {
    try {
      const [toolsPayload, invPayload, agentsPayload] = await Promise.all([
        fetchJson<{ tools?: Tool[] }>(`${apiBase}/api/tools`, requestOptions("GET")),
        fetchJson<{ investigations?: Investigation[] }>(`${apiBase}/api/investigations${showArchived ? "?include_archived=true" : ""}`, requestOptions("GET")),
        fetchJson<{ agents?: Agent[] }>(`${apiBase}/api/agents`, requestOptions("GET")),
      ]);
      setTools(toolsPayload.tools ?? []);
      setInvestigations(invPayload.investigations ?? []);
      setAgents(agentsPayload.agents ?? []);
      setApiStatus("online");
      fetchJson<SystemStatus | null>(`${apiBase}/api/system/status`, requestOptions("GET"))
        .then((payload) => setSystemStatus(payload))
        .catch(() => setSystemStatus(null));
    } catch (exc) {
      setApiStatus("offline");
      setError(exc instanceof Error ? exc.message : "API 请求失败");
    }
  }

  useEffect(() => {
    refresh().catch(() => setApiStatus("offline"));
  }, [showArchived]);

  const investigationsRef = useRef(investigations);
  investigationsRef.current = investigations;

  // Auto-refresh every 8s when there are active tasks
  useEffect(() => {
    const id = setInterval(async () => {
      const hasActive = investigationsRef.current.some((inv) => isActiveInvestigationStatus(inv.status));
      if (!hasActive) return;
      await refresh();
      if (selectedIdRef.current) {
        try {
          const payload = await fetchJson<Investigation>(`${apiBase}/api/investigations/${selectedIdRef.current}`, requestOptions("GET"));
          setSelected((prev) => prev ? { ...prev, ...payload } : null);
        } catch (exc) {
          setError(exc instanceof Error ? exc.message : "任务详情刷新失败");
        }
      }
    }, 8000);
    return () => clearInterval(id);
  }, [showArchived]);

  const enabledTools = useMemo(() => tools.filter((t) => t.enabled_by_default), [tools]);

  async function createInvestigation(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const intelligenceRequirements = {
      decision_context: requirementsForm.decision_context,
      confidence_requirement: requirementsForm.confidence_requirement,
      pirs: [],
      eeis: [],
    };
    const sparseMetadata = form.seed_type === "sparse_lead" ? buildSparseLeadMetadata(sparseLeadForm) : null;
    const payload = sparseMetadata
      ? {
          ...form,
          name: form.name || `弱线索买家：${sparseMetadata.lead_display_name || sparseMetadata.member_id}`,
          seed_value: sparseLeadSeedValue(sparseMetadata),
          metadata: { ...sparseMetadata, intelligence_requirements: intelligenceRequirements },
        }
      : { ...form, metadata: { intelligence_requirements: intelligenceRequirements } };
    try {
      await fetchJson(`${apiBase}/api/investigations`, {
        ...requestOptions("POST", csrfToken ?? undefined),
        body: JSON.stringify(payload),
      });
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法创建调查任务");
    }
  }

  async function loadInvestigation(id: string) {
    setLoadingDetail(true);
    selectedIdRef.current = id;
    try {
      const payload = await fetchJson<Investigation>(`${apiBase}/api/investigations/${id}`, requestOptions("GET"));
      const dp = findDecisionProfileForInvestigation(payload, investigations);
      const loadedDp = dp ? await fetchJson<Investigation>(`${apiBase}/api/investigations/${dp.id}`, requestOptions("GET")) : null;
      setSelected({ ...payload, decision_profile: loadedDp ?? undefined, combined_graph: combineGraphs(payload.graph, loadedDp?.graph) });
      window.requestAnimationFrame(() => dataBoardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "任务详情加载失败");
    } finally {
      setLoadingDetail(false);
    }
  }

  async function postInvestigationAction(id: string, action: "cancel" | "reopen" | "retry" | "archive" | "delete") {
    setError(null);
    let updated;
    try {
      updated = await fetchJson<Investigation & { deleted?: boolean }>(
        `${apiBase}/api/investigations/${id}/${action}`,
        requestOptions("POST", csrfToken ?? undefined),
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "任务操作失败");
      return;
    }
    if (action === "delete") { if (selected?.id === id) { setSelected(null); selectedIdRef.current = null; } }
    else { setSelected(updated); }
    await refresh();
  }

  function requestAction(id: string, action: "cancel" | "reopen" | "retry" | "archive" | "delete") {
    if (action === "delete") {
      setConfirm({ title: "确认删除", message: "删除后无法恢复，确定要删除这条调查任务吗？", confirmLabel: "删除", danger: true, onConfirm: () => { setConfirm(null); postInvestigationAction(id, action); } });
    } else if (action === "cancel") {
      setConfirm({ title: "确认取消", message: "取消后任务将停止执行，确定要取消吗？", confirmLabel: "取消任务", danger: true, onConfirm: () => { setConfirm(null); postInvestigationAction(id, action); } });
    } else {
      postInvestigationAction(id, action);
    }
  }

  async function releaseStaleClaims() {
    setError(null);
    try {
      await fetchJson(`${apiBase}/api/investigations/release-stale`, {
        ...requestOptions("POST", csrfToken ?? undefined),
        body: JSON.stringify({ stale_after_seconds: 1800 }),
      });
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "释放过期认领失败");
    }
  }

  async function runSelectedJobs() {
    if (!selected) return;
    setError(null); setRunningJobs(true);
    try {
      const payload = await fetchJson<{ busy?: boolean }>(`${apiBase}/api/investigations/${selected.id}/run-jobs`, {
        ...requestOptions("POST", csrfToken ?? undefined),
        body: JSON.stringify({}),
      });
      if (payload.busy) {
        setError("当前任务已有运行中的队列，请等待完成或释放过期认领后再运行。");
      }
      await refresh(); await loadInvestigation(selected.id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "运行队列失败");
    } finally { setRunningJobs(false); }
  }

  const selectedMetrics: DataMetric[] = selected ? [
    { label: "实体", value: selected.entities?.length ?? 0 },
    { label: "事实", value: selected.facts?.length ?? 0 },
    { label: "证据账本", value: selected.evidence_ledger?.length ?? 0 },
    { label: "关系", value: selected.relationships?.length ?? 0 },
    { label: "置信度", value: selected.confidence === null ? "-" : selected.confidence.toFixed(2) },
  ] : [];
  const cockpitMetrics = buildCockpitMetrics(selected);
  const selectedBluf = cockpitBluf(selected);
  const hasReport = Boolean(selected?.report_markdown?.trim());
  const hasConfirmedMemory = Boolean(
    (selected?.intelligence_memory?.confirmed_findings?.length ?? 0) ||
      (selected?.intelligence_memory?.review_findings?.length ?? 0),
  );
  const compactGaps = selected?.intelligence_memory?.collection_gaps?.slice(0, 3) ?? [];
  const hasAuditData = Boolean(
    selected &&
    ((selected.facts?.length ?? 0) ||
      (selected.evidence_ledger?.length ?? 0) ||
      (selected.hypotheses?.length ?? 0) ||
      selected.report_markdown?.trim() ||
      hasConfirmedMemory),
  );
  const activeJobs = selected?.jobs?.filter((job) => ["OPEN", "CLAIMED", "RUNNING", "STALE_CLAIM"].includes(job.status)) ?? [];
  const evidenceLedgerCards = selected?.evidence_ledger?.slice(0, 4) ?? [];
  const factCards = selected?.facts?.slice(0, 2) ?? [];
  const topEntities = selected?.entities?.slice(0, 3) ?? [];
  const h1Score = selected?.hypotheses?.[0]?.support_score ?? selected?.confidence ?? null;
  const h2Score = selected?.hypotheses?.[1]?.inconsistency_score ?? selected?.risk_report?.overall_risk_score ?? null;
  const organizationLabel = preferredOrganizationLabel(
    selected?.entities,
    selected?.seed_value ?? "目标企业代号/名称",
  );
  const decisionLabel = preferredDecisionLabel(
    selected?.entities,
    selected?.seed_value ?? "买家/决策人姓名",
  );
  const productLabel =
    selected?.entities?.find((entity) => ["product_scope", "purchase_category", "business_scope"].includes(entity.type))?.value ??
    "核心主营产品线";
  const locationLabel =
    selected?.entities?.find((entity) => ["country_region", "declared_location", "likely_activity_region", "address"].includes(entity.type))?.value ??
    "注册国家/常驻地";
  const contactLabel =
    selected?.entities?.find((entity) => ["email", "phone"].includes(entity.type))?.value ??
    "联系电话 / WhatsApp";
  const statusText = selected ? labelOf(taskStateLabels, selected.status) : "待选择";
  const gapCards = compactGaps.length
    ? compactGaps
    : [
        { key: "persona", label: "决策人核轨迹深挖", reason: "补全姓名、职位、公开主页与联系习惯" },
        { key: "enterprise", label: "组织资产核供应链穿透", reason: "补全开票实体、交割地址与上下游证据" },
      ];

  const primaryInvestigations = visiblePrimaryInvestigations(investigations as BundleInvestigation[]) as Investigation[];
  const filteredInvestigations = primaryInvestigations.filter((item) => {
    if (stateFilter === "all") return true;
    if (stateFilter === "active") return isActiveInvestigationStatus(item.status);
    if (stateFilter === "done") return isReviewableInvestigationStatus(item.status);
    if (stateFilter === "failed") return ["FAILED", "CANCELLED"].includes(item.status);
    return item.status === stateFilter;
  });

  const statusDot = apiStatus === "online" ? "status-dot-online" : apiStatus === "offline" ? "status-dot-offline" : "status-dot-checking";
  const defaultInvestigation = chooseDefaultInvestigation(primaryInvestigations);

  useEffect(() => {
    if (selectedIdRef.current || loadingDetail || !defaultInvestigation) return;
    loadInvestigation(defaultInvestigation.id);
  }, [defaultInvestigation, loadingDetail]);

  return (
    <main className="shell">
      {confirm ? (
        <ConfirmDialog
          title={confirm.title}
          message={confirm.message}
          confirmLabel={confirm.confirmLabel}
          danger={confirm.danger}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      ) : null}

      <aside className="sidebar">
        <div className="brand">
          <img src="/logo.png" alt="皇城司 HCS" />
          <div><strong>皇城司 HCS</strong><span>企业情报与证据图谱中枢</span></div>
        </div>
        <nav>
          <a className="active"><Activity size={18} />任务池</a>
          <a aria-disabled="true" title="即将上线"><Search size={18} />Agent 接入</a>
          <a aria-disabled="true" title="即将上线"><GitBranch size={18} />证据图谱</a>
          <a aria-disabled="true" title="即将上线"><Cpu size={18} />工具管理</a>
          <a aria-disabled="true" title="即将上线"><Database size={18} />报告库</a>
        </nav>
        {onLogout ? (
          <button className="logout-button" type="button" onClick={onLogout} aria-label="退出登录" title="退出登录">
            <LogOut size={18} />
          </button>
        ) : null}
      </aside>

      <section className="workspace">
        <section className="panel data-board" ref={dataBoardRef}>
          <div className="hcs-intel-bar">
            <div className="hcs-core-mark" aria-hidden="true">
              <span>CORE</span>
              <strong>02</strong>
            </div>
            <div className="hcs-intel-title">
              <div className="hcs-kicker-row">
                <span className="hcs-kicker">DUAL-CORE STANDARD TEMPLATE</span>
                {selected ? <span className={statusClass(selected.status)}>{statusText}</span> : null}
              </div>
              <h2>{selected ? selected.name : "皇城司 (HCS) 双核心人企协同决策舱 · 通用模板"}</h2>
              <code>{selected ? `${labelOf(targetTypeLabels, selected.seed_type)}: ${selected.seed_value}` : "选择任务后载入组织资产核与意志决策核"}</code>
              {selected && isSparseLeadInvestigation(selected.seed_type) ? (
                <div className="stage-strip hcs-stage-strip">
                  {sparseLeadStages(selected.jobs ?? []).map((stage) => (
                    <span key={stage.key} className={`stage-chip stage-${stage.status.toLowerCase()}`}>
                      {stage.label}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="hcs-bluf">
              <span>[BLUF 核心研判裁决结论]</span>
              <p>{selectedBluf}</p>
            </div>
            <div className="hcs-metric-strip">
              {[cockpitMetrics[0], cockpitMetrics[3] ?? cockpitMetrics[1]].filter(Boolean).map((metric) => (
                <div key={metric.label} className={`hcs-metric${metric.tone ? ` hcs-metric-${metric.tone}` : ""}`}>
                  <span>{metric.label === "缺口" ? "缺口闭合率" : metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
          </div>
          {loadingDetail ? <div className="loading-bar" /> : null}
          {selected ? (
            <div className={`hcs-cockpit${loadingDetail ? " detail-loading" : ""}`}>
              <details className="hcs-left-rail hcs-left-drawer">
                <summary>
                  <span>证据 / 实体</span>
                  <strong>{(selected.evidence_ledger?.length ?? 0) + (selected.entities?.length ?? 0)}</strong>
                </summary>
                <div className="hcs-left-drawer-body">
                  <article className="core-v2-panel hcs-ledger-panel">
                    <div className="section-heading">
                      <h3>Evidence Ledger / 交叉验证事实账本流</h3>
                      <span>信度评级</span>
                    </div>
                    <div className="hcs-ledger-list">
                      {evidenceLedgerCards.map((item, index) => (
                        <article key={item.id} className={`hcs-ledger-card hcs-ledger-${index % 4}`}>
                          <div>
                            <span>[组织核 · {item.source_type || "公开来源"}]</span>
                            <strong>{item.admiralty_code || "Admiralty Code"}</strong>
                          </div>
                          <p>{item.snippet || item.source_url}</p>
                        </article>
                      ))}
                      {factCards.map((fact, index) => (
                        <article key={fact.id} className={`hcs-ledger-card hcs-ledger-${(index + 2) % 4}`}>
                          <div>
                            <span>[事实池 · {fact.predicate || "交叉验证"}]</span>
                            <strong>{fact.status || fact.admiralty_code || "待复核"}</strong>
                          </div>
                          <p>{fact.statement}</p>
                        </article>
                      ))}
                      {!evidenceLedgerCards.length && !factCards.length ? (
                        <>
                          <article className="hcs-ledger-card hcs-ledger-1">
                            <div><span>[组织核 · 证据账本]</span><strong>待回写</strong></div>
                            <p>证据账本未回写，等待 Agent 补全可追溯来源。</p>
                          </article>
                          <article className="hcs-ledger-card hcs-ledger-2">
                            <div><span>[意志核 · 事实池]</span><strong>待闭合</strong></div>
                            <p>事实池未闭合，当前以 BLUF、任务队列与图谱状态作为研判入口。</p>
                          </article>
                        </>
                      ) : null}
                    </div>
                  </article>
                  <article className="core-v2-panel hcs-brief-card">
                    <div className="section-heading">
                      <h3>关键实体</h3>
                      <span>{selected.entities?.length ?? 0} 条</span>
                    </div>
                    <div className="detail-stack compact-stack">
                      {topEntities.map((entity) => (
                        <DataRow key={entity.id} title={`${labelOf(entityTypeLabels, entity.type)}：${entity.value}`} meta={`${entity.source_tool} / ${entity.confidence.toFixed(2)}`} />
                      ))}
                      {!topEntities.length ? <div className="empty compact">暂无实体。</div> : null}
                    </div>
                  </article>
                </div>
              </details>
              <section className="hcs-column hcs-graph-core">
                <HcsTemplateGraph
                  organizationLabel={organizationLabel}
                  decisionLabel={decisionLabel}
                  productLabel={productLabel}
                  locationLabel={locationLabel}
                  contactLabel={contactLabel}
                  summary={selected.summary}
                  entities={selected.entities}
                  evidence={selected.evidence}
                  evidenceLedger={selected.evidence_ledger}
                  facts={selected.facts}
                  relationships={selected.relationships}
                  riskReport={selected.risk_report}
                  gaps={selected.intelligence_memory?.collection_gaps}
                  entityCount={selected.entities?.length ?? 0}
                  evidenceCount={(selected.evidence?.length ?? 0) + (selected.evidence_ledger?.length ?? 0)}
                  relationshipCount={selected.relationships?.length ?? 0}
                />
                <MosaicEvidenceChain
                  entities={selected.entities}
                  evidence={selected.evidence}
                  relationships={selected.relationships}
                />
                <IntelligencePanel
                  investigation={selected}
                  apiBase={apiBase}
                  requestHeaders={csrfHeaders}
                />
                {selected.seed_type === "company" && (
                  <SupplyChainPanel
                    investigation={selected}
                    apiBase={apiBase}
                    requestHeaders={csrfHeaders}
                  />
                )}
              </section>
              <details className="hcs-right-rail hcs-right-drawer">
                <summary>
                  <span>验证 / 队列</span>
                  <strong>{(selected.hypotheses?.length ?? 0) + (selected.jobs?.length ?? 0)}</strong>
                </summary>
                <div className="hcs-right-drawer-body">
                  <IntelligenceRequirementsPanel requirements={selected.intelligence_requirements} />
                  <HypothesisPanel hypotheses={selected.hypotheses} analysis={selected.hypothesis_analysis} />
                  <RiskReviewPanel riskReport={selected.risk_report ?? {}} />
                  <QueuePanel jobCounts={selected.job_counts ?? {}} jobs={selected.jobs ?? []} running={runningJobs} onRun={runSelectedJobs} />
                  <div className="hcs-agent-pipeline">
                    <div className="section-heading">
                      <h3>智能体节点池</h3>
                      <span>{agents.length} 个</span>
                    </div>
                    <div className="hcs-pipeline-list">
                      {agents.slice(0, 4).map((agent) => (
                        <div key={agent.id} className="hcs-pipeline-row">
                          <div>
                            <strong>{agent.agent_name}</strong>
                            <span>{labelOf(agentRoleLabels, agent.agent_type)}</span>
                          </div>
                          <em>{agent.status}</em>
                        </div>
                      ))}
                      {!agents.length ? <div className="empty compact">暂无 Agent 注册。</div> : null}
                    </div>
                  </div>
                </div>
              </details>
              <section className="hcs-assessment">
                <article className={`report-card hcs-whitepaper${hasReport ? "" : " hcs-whitepaper-empty"}`}>
                  <h3>皇城司双核协同情报评估白皮书</h3>
                  {hasReport ? (
                    <div className="report-markdown" dangerouslySetInnerHTML={{ __html: sanitizeReportHtml(marked.parse(selected.report_markdown) as string) }} />
                  ) : (
                    <div className="report-markdown">
                      <p>暂无正文报告。当前任务优先查看 BLUF、图谱、队列和风险复核；完整报告生成后会在这里展开。</p>
                    </div>
                  )}
                </article>
                <QualityGatePanel
                  assessment={selected.quality_assessment}
                  memory={selected.intelligence_memory}
                  jobs={selected.jobs}
                />
                <div className="hcs-gap-stack">
                  {hasAuditData ? (
                    <>
                      <article className="core-v2-panel hcs-brief-card">
                        <div className="section-heading">
                          <h3>PIR Intelligence Gaps / 核心缺口拦截探针中枢</h3>
                          <span>{gapCards.length} 项</span>
                        </div>
                        <div className="hcs-gap-list">
                          {gapCards.map((gap) => (
                            <span key={gap.key}><strong>{gap.label}</strong>{gap.reason ? ` / ${gap.reason}` : ""}</span>
                          ))}
                        </div>
                      </article>
                      <CrossVerificationMatrixPanel rows={selected.cross_verification_matrix} />
                      <FactPromotionPanel facts={selected.facts} />
                      <ReportAuditPanel
                        facts={selected.facts}
                        evidenceLedger={selected.evidence_ledger}
                        hypotheses={selected.hypotheses}
                        analysis={selected.hypothesis_analysis}
                        memory={selected.intelligence_memory}
                        reportMarkdown={selected.report_markdown}
                      />
                    </>
                  ) : (
                    <article className="core-v2-panel hcs-brief-card">
                      <div className="section-heading">
                        <h3>PIR 缺口池</h3>
                        <span>{gapCards.length || activeJobs.length} 项</span>
                      </div>
                      <div className="hcs-gap-list">
                        {gapCards.map((gap) => (
                          <span key={gap.key}>{gap.label}</span>
                        ))}
                      </div>
                    </article>
                  )}
                  {hasConfirmedMemory ? <IntelligenceMemoryPanel memory={selected.intelligence_memory} /> : null}
                </div>
              </section>
              <section className="hcs-overflow-data">
                <MiniMetrics metrics={selectedMetrics} />
                <details className="hcs-raw-details">
                  <summary>展开原始实体 / 证据 / 关系明细</summary>
                  <div className="hcs-overflow-grid">
                  <article className="core-v2-panel">
                    <div className="section-heading"><h3>实体</h3><span>{selected.entities?.length ?? 0} 条</span></div>
                    <div className="detail-stack">
                      {(selected.entities ?? []).slice(0, 8).map((entity) => (
                        <DataRow key={entity.id} title={`${labelOf(entityTypeLabels, entity.type)}：${entity.value}`} meta={`${entity.source_tool} / ${entity.confidence.toFixed(2)}`} />
                      ))}
                      {!(selected.entities ?? []).length ? <div className="empty compact">暂无实体。</div> : null}
                    </div>
                  </article>
                  <article className="core-v2-panel">
                    <div className="section-heading"><h3>证据</h3><span>{selected.evidence?.length ?? 0} 条</span></div>
                    <div className="detail-stack">
                      {(selected.evidence ?? []).slice(0, 6).map((item) => (
                        <DataRow key={item.id} title={item.entity_value} meta={`${item.source_tool} / ${labelOf(evidenceKindLabels, item.evidence_kind)}`} body={item.snippet} />
                      ))}
                      {!(selected.evidence ?? []).length ? <div className="empty compact">暂无证据。</div> : null}
                    </div>
                  </article>
                  <article className="core-v2-panel">
                    <div className="section-heading"><h3>关系</h3><span>{selected.relationships?.length ?? 0} 条</span></div>
                    <div className="detail-stack">
                      {(selected.relationships ?? []).slice(0, 8).map((r) => (
                        <DataRow key={r.id} title={`${r.from_value} → ${r.to_value}`} meta={`${labelOf(relationshipTypeLabels, r.relationship_type)} / ${r.confidence.toFixed(2)}`} />
                      ))}
                      {!(selected.relationships ?? []).length ? <div className="empty compact">暂无关系。</div> : null}
                    </div>
                  </article>
                  </div>
                </details>
              </section>
            </div>
          ) : (
            <div className="data-board-empty-state">
              <div>
                <strong>尚未选择调查任务</strong>
                <span>从任务池载入现有调查，或先创建调查任务。</span>
              </div>
              <a
                className="secondary-button data-board-empty-action"
                href="#create-investigation-form"
                onClick={() => {
                  setOperationsOpen(true);
                  window.requestAnimationFrame(() => createFormRef.current?.focus());
                }}
              >
                创建调查任务
              </a>
            </div>
          )}
        </section>

        <details
          className="ops-console"
          open={operationsOpen}
          onToggle={(event) => setOperationsOpen(event.currentTarget.open)}
        >
          <summary className="ops-console-summary">
            <span>任务与操作台</span>
            <strong>创建任务 / Agent 状态 / 任务池</strong>
            <em className={`status-pill status-pill-api`}>
              <span className={`status-dot ${statusDot}`} />
              {apiStatus === "online" ? "API 在线" : apiStatus === "offline" ? "API 离线" : "连接中…"}
            </em>
          </summary>
          <div className="ops-console-body">
          <section className="metric-grid">
              <Metric label="开放任务" value={primaryInvestigations.filter((i) => i.status === "OPEN").length} />
              <Metric label="在线 Agent" value={agents.length} />
              <Metric label="工具能力" value={enabledTools.length} />
              <Metric label="执行模式" value="Agent 接管" />
            </section>
            <SystemStatusPanel status={systemStatus} />
  
          <section className="content-grid">
            <form
              id="create-investigation-form"
              ref={createFormRef}
              className="panel form-panel"
              tabIndex={-1}
              onSubmit={createInvestigation}
            >
              <div className="panel-heading">
                <h2>创建开放任务</h2>
                <button type="submit"><Play size={16} />发布</button>
              </div>
              <label>任务名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
              <div className="form-row">
                <label>目标类型
                  <select value={form.seed_type} onChange={(e) => setForm({ ...form, seed_type: e.target.value })}>
                    <option value="domain">域名</option><option value="email">邮箱</option>
                    <option value="username">用户名</option><option value="phone">手机号</option>
                    <option value="company">企业</option><option value="sparse_lead">弱线索买家</option>
                  </select>
                </label>
                <label>采集策略
                  <select value={form.strategy} onChange={(e) => setForm({ ...form, strategy: e.target.value })}>
                    <option value="quick">快速</option><option value="standard">标准</option>
                    <option value="deep">深度</option><option value="maximum">最大召回</option>
                  </select>
                </label>
              </div>
              <label>目标值<input className="mono" value={form.seed_value} onChange={(e) => setForm({ ...form, seed_value: e.target.value })} /></label>
              <div className="intel-requirement-mini">
                <label>情报用途
                  <input
                    value={requirementsForm.decision_context}
                    onChange={(e) => setRequirementsForm({ ...requirementsForm, decision_context: e.target.value })}
                  />
                </label>
                <label>置信要求
                  <select
                    value={requirementsForm.confidence_requirement}
                    onChange={(e) => setRequirementsForm({ ...requirementsForm, confidence_requirement: e.target.value })}
                  >
                    <option value="quick">快速判断</option>
                    <option value="standard">标准闭环</option>
                    <option value="strict">严格证据</option>
                  </select>
                </label>
              </div>
              {form.seed_type === "sparse_lead" ? (
                <div className="sparse-lead-grid">
                  <label>平台<input value={sparseLeadForm.platform} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, platform: e.target.value })} /></label>
                  <label>显示名<input value={sparseLeadForm.lead_display_name} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, lead_display_name: e.target.value })} /></label>
                  <label>会员 ID<input className="mono" value={sparseLeadForm.member_id} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, member_id: e.target.value })} /></label>
                  <label>国家/地区<input value={sparseLeadForm.country_region} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, country_region: e.target.value })} /></label>
                  <label>注册年份<input value={sparseLeadForm.registration_year} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, registration_year: e.target.value })} /></label>
                  <label>原始公司字段<input value={sparseLeadForm.company_name_raw} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, company_name_raw: e.target.value })} /></label>
                  <label className="wide-field">类目<textarea value={sparseLeadForm.categoriesText} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, categoriesText: e.target.value })} /></label>
                  <label className="wide-field">近期 RFQ<textarea value={sparseLeadForm.recentRfqsText} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, recentRfqsText: e.target.value })} /></label>
                  <label className="wide-field">备注<textarea value={sparseLeadForm.operator_notes} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, operator_notes: e.target.value })} /></label>
                </div>
              ) : null}
              {error ? <div className="error"><AlertTriangle size={16} />{error}</div> : null}
            </form>
  
            <section className="panel">
              <div className="panel-heading">
                <h2>Agent 状态</h2>
                <span>已注册 {agents.length} 个</span>
              </div>
              <div className="tool-list">
                {agents.map((agent) => (
                  <article key={agent.id} className="tool-row">
                    <div><strong>{agent.agent_name}</strong><span>{agent.agent_type}</span></div>
                    <code>{agent.capabilities.join("、")}</code>
                    <span className="ok">{agent.status}</span>
                  </article>
                ))}
                {!agents.length ? <div className="empty compact">暂无 Agent 注册。Codex、OpenHuman 或任意 CLI 可通过协议接口接入。</div> : null}
              </div>
            </section>
          </section>
  
          <section className="panel">
            <div className="panel-heading">
              <h2>任务池</h2>
              <div className="heading-actions">
                <span>显示 {filteredInvestigations.length} / {primaryInvestigations.length} 个</span>
                <button type="button" className="secondary-button" onClick={releaseStaleClaims}>
                  <RefreshCcw size={16} />释放过期认领
                </button>
              </div>
            </div>
            <div className="filter-bar">
              <label>
                <Filter size={16} />状态筛选
                <select value={stateFilter} onChange={(e) => setStateFilter(e.target.value)}>
                  <option value="active">活跃任务</option><option value="done">结果/待复核</option>
                  <option value="failed">失败/已取消</option><option value="all">全部状态</option>
                  <option value="OPEN">开放认领</option><option value="CLAIMED">已认领</option>
                  <option value="RUNNING">运行中</option><option value="NEEDS_REVIEW">待复核</option><option value="COMPLETED">已完成</option>
                  <option value="ARCHIVED">已归档</option>
                </select>
              </label>
              <label className="checkbox-line">
                <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
                显示归档任务
              </label>
            </div>
            <table>
              <thead>
                <tr><th>名称</th><th>目标</th><th>策略</th><th>状态</th><th>执行 Agent</th><th>置信度</th><th>操作</th></tr>
              </thead>
              <tbody>
                {filteredInvestigations.map((item) => (
                  <tr key={item.id} className={selectedTaskRowClassName(item.id, selected?.id ?? null)} onClick={() => loadInvestigation(item.id)}>
                    <td>{item.name}</td>
                    <td><code>{labelOf(targetTypeLabels, item.seed_type)}：{item.seed_value}</code></td>
                    <td>{labelOf(strategyLabels, item.strategy)}</td>
                    <td><span className={statusClass(item.status)}>{labelOf(taskStateLabels, item.status)}</span></td>
                    <td>{item.claimed_by_agent_name ?? "未认领"}</td>
                    <td>{item.confidence === null ? "-" : item.confidence.toFixed(2)}</td>
                    <td><TaskActions item={item} onAction={requestAction} /></td>
                  </tr>
                ))}
                {!filteredInvestigations.length ? <tr><td colSpan={7} className="empty">暂无开放任务。</td></tr> : null}
              </tbody>
            </table>
          </section>
          </div>
        </details>
      </section>
    </main>
  );
}

const rootElement = document.getElementById("root");
if (rootElement) createRoot(rootElement).render(<App />);
