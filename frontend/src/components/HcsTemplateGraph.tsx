import { type KeyboardEvent, useMemo, useState } from "react";
import { preferredDecisionLabel, preferredOrganizationLabel } from "../hcs-graph-data";
import type { Entity, EvidenceItem, EvidenceLedgerRecord, FactRecord, IntelligenceMemoryGap, Relationship, RiskReport } from "../types";

type HcsTemplateGraphProps = {
  organizationLabel: string;
  decisionLabel: string;
  productLabel: string;
  locationLabel: string;
  contactLabel: string;
  summary?: string;
  entities?: Entity[];
  evidence?: EvidenceItem[];
  evidenceLedger?: EvidenceLedgerRecord[];
  facts?: FactRecord[];
  relationships?: Relationship[];
  riskReport?: RiskReport;
  gaps?: IntelligenceMemoryGap[];
  entityCount?: number;
  evidenceCount?: number;
  relationshipCount?: number;
};

type GraphNodeInfo = {
  id: string;
  title: string;
  subtitle: string;
  body: string;
  items?: string[];
  tone: "blue" | "green" | "red" | "amber" | "cyan" | "slate";
};

const businessTypes = new Set(["organization", "company_name_raw", "business_scope", "market_coverage"]);
const productTypes = new Set(["product_scope", "purchase_category", "business_scope", "rfq_text"]);
const contactTypes = new Set(["email", "phone", "domain", "profile_url", "external_link", "social_profile"]);
const locationTypes = new Set(["country_region", "declared_location", "likely_activity_region", "address"]);
const personaTypes = new Set(["identity", "username", "platform_account", "platform_member_id", "public_personal_attribute"]);

function uniqueValues(values: Array<string | undefined | null>, limit = 4) {
  return Array.from(new Set(values.map((value) => value?.trim()).filter(Boolean) as string[])).slice(0, limit);
}

function entityValues(entities: Entity[], types: Set<string>, limit = 4) {
  return uniqueValues(entities.filter((entity) => types.has(entity.type)).map((entity) => entity.value), limit);
}

function prioritizedEntityValues(entities: Entity[], preferred: string, types: Set<string>, limit = 4) {
  const values = entityValues(entities, types, limit + 1);
  return uniqueValues([preferred, ...values], limit);
}

function evidenceSnippets(evidence: EvidenceItem[], ledger: EvidenceLedgerRecord[], keywords: string[], limit = 3) {
  const haystack = [...evidence.map((item) => item.snippet || item.entity_value), ...ledger.map((item) => item.snippet || item.source_url)];
  const matched = haystack.filter((value) => {
    const text = value.toLowerCase();
    return keywords.some((keyword) => text.includes(keyword.toLowerCase()));
  });
  return uniqueValues(matched.length ? matched : haystack, limit);
}

function riskSummaries(riskReport: RiskReport | undefined, keywords: string[], limit = 3) {
  const signals = riskReport?.top_risk_signals ?? [];
  const matched = signals.filter((signal) => {
    const text = `${signal.kind} ${signal.summary} ${(signal.evidence_values ?? []).join(" ")}`.toLowerCase();
    return keywords.some((keyword) => text.includes(keyword.toLowerCase()));
  });
  return uniqueValues((matched.length ? matched : signals).map((signal) => `${signal.kind}: ${signal.summary}`), limit);
}

function relationshipSummaries(relationships: Relationship[], keywords: string[], limit = 3) {
  const matched = relationships.filter((rel) => {
    const text = `${rel.from_value} ${rel.to_value} ${rel.relationship_type}`.toLowerCase();
    return keywords.some((keyword) => text.includes(keyword.toLowerCase()));
  });
  return uniqueValues((matched.length ? matched : relationships).map((rel) => `${rel.from_value} -> ${rel.to_value}`), limit);
}

function describeItems(items: string[], fallback: string) {
  return items.length ? items.join("；") : fallback;
}

export function HcsTemplateGraph({
  organizationLabel,
  decisionLabel,
  productLabel,
  locationLabel,
  contactLabel,
  summary = "",
  entities = [],
  evidence = [],
  evidenceLedger = [],
  facts = [],
  relationships = [],
  riskReport,
  gaps = [],
  entityCount = 0,
  evidenceCount = 0,
  relationshipCount = 0,
}: HcsTemplateGraphProps) {
  const [zoom, setZoom] = useState(1);
  const [selectedId, setSelectedId] = useState("organization-core");

  const nodes = useMemo<GraphNodeInfo[]>(() => {
    const preferredOrganization = preferredOrganizationLabel(entities, organizationLabel);
    const preferredDecision = preferredDecisionLabel(entities, decisionLabel);
    const business = prioritizedEntityValues(entities, preferredOrganization, businessTypes);
    const products = entityValues(entities, productTypes);
    const contacts = entityValues(entities, contactTypes);
    const locations = entityValues(entities, locationTypes);
    const personas = prioritizedEntityValues(entities, preferredDecision, personaTypes);
    const offshoreRisks = riskSummaries(riskReport, ["国家", "地区", "Germany", "Netherlands", "主体", "名称", "矛盾", "冲突"]);
    const manufacturingEvidence = evidenceSnippets(evidence, evidenceLedger, ["工厂", "制造", "员工", "面积", "factory", "production"]);
    const productEvidence = evidenceSnippets(evidence, evidenceLedger, ["包装", "材料", "产品", "category", "rfq", "business"]);
    const contactEvidence = evidenceSnippets(evidence, evidenceLedger, ["@", "电话", "phone", "email", "whatsapp", "contact"]);
    const landedEvidence = [...business, ...locations, ...relationshipSummaries(relationships, ["company", "organization", "address", "BV", "LLC"])];
    const activityGaps = gaps.map((gap) => `${gap.label}: ${gap.reason}`);

    return [
      {
        id: "organization-core",
        title: "组织资产核",
        subtitle: preferredOrganization,
        body: `承载企业主体、经营资产、产品线、供应链与数字足迹。当前图谱实体 ${entityCount} 个、证据 ${evidenceCount} 条、关系 ${relationshipCount} 条。`,
        items: business.length ? business : relationshipSummaries(relationships, [preferredOrganization]),
        tone: "blue",
      },
      {
        id: "offshore-shell",
        title: "宣称海外总部 / 离岸外壳",
        subtitle: offshoreRisks[0] ?? "主体冲突检查点",
        body: describeItems(offshoreRisks, "用于标记海外总部、离岸外壳、工商主体、开票主体之间是否存在断链或互相矛盾。"),
        items: offshoreRisks,
        tone: "red",
      },
      {
        id: "manufacturing-base",
        title: "宣称智能制造基地",
        subtitle: manufacturingEvidence[0] ?? "营销泡沫检查点",
        body: describeItems(manufacturingEvidence, "用于核对制造基地、工厂面积、员工规模、产能描述与可验证工商/平台/地址证据是否一致。"),
        items: manufacturingEvidence,
        tone: "amber",
      },
      {
        id: "product-line",
        title: "核心主营产品线",
        subtitle: products[0] ?? productLabel,
        body: describeItems([...products, ...productEvidence], "用于聚合主营产品、采购类目、业务范围和可成交品类，辅助判断双方业务匹配度。"),
        items: [...products, ...productEvidence].slice(0, 4),
        tone: "green",
      },
      {
        id: "digital-footprint",
        title: "数字踪迹 / 代运营网络",
        subtitle: contacts[0] ?? "邮箱 / 电话 / 地址",
        body: describeItems([...contacts, ...contactEvidence], "用于收束邮箱、电话、客服、代运营公司、交割地址、域名和平台账号等数字痕迹。"),
        items: [...contacts, ...contactEvidence].slice(0, 4),
        tone: "cyan",
      },
      {
        id: "landed-entity",
        title: "穿透落地经营实体名称",
        subtitle: landedEvidence[0] ?? "年限 / 员工规模 / 工厂面积",
        body: describeItems(landedEvidence, "用于落地真实经营主体，核对平台年限、人员规模、地址、工厂资产和实体证据。"),
        items: landedEvidence.slice(0, 4),
        tone: "slate",
      },
      {
        id: "decision-core",
        title: "意志决策核",
        subtitle: personas[0] ?? preferredDecision,
        body: summary || describeItems(personas, "承载买家/决策人身份、行动意图、询盘行为、联系路径和拦截部署。"),
        items: personas,
        tone: "green",
      },
      {
        id: "persona-role",
        title: "真实姓名 / 高管职位",
        subtitle: personas[0] ?? preferredDecision,
        body: describeItems([...personas, ...relationshipSummaries(relationships, ["manager", "representative", "principal", "identity", "role"])], "用于确认决策人姓名、职位、授权关系、公开主页和企业内角色。"),
        items: personas,
        tone: "slate",
      },
      {
        id: "contact-channel",
        title: "联系电话 / WhatsApp",
        subtitle: contacts[0] ?? contactLabel,
        body: describeItems([...contacts, ...contactEvidence], "用于沉淀电话、邮箱、WhatsApp、LinkedIn 或其他可触达路径，并区分归属边界。"),
        items: [...contacts, ...contactEvidence].slice(0, 4),
        tone: "slate",
      },
      {
        id: "location",
        title: "注册国家 / 常驻地",
        subtitle: locations[0] ?? locationLabel,
        body: describeItems([...locations, ...offshoreRisks], "用于核验注册地、常驻地、时区、贸易地和公开目录所在地是否一致。"),
        items: [...locations, ...offshoreRisks].slice(0, 4),
        tone: "green",
      },
      {
        id: "activity-habit",
        title: "活跃频次 / 联系习惯",
        subtitle: activityGaps[0] ?? "待补全",
        body: describeItems(activityGaps, "用于记录平台活跃、询盘节奏、历史采购行为和最佳触达窗口。"),
        items: activityGaps.slice(0, 4),
        tone: "slate",
      },
    ];
  }, [contactLabel, decisionLabel, entities, entityCount, evidence, evidenceCount, evidenceLedger, gaps, locationLabel, organizationLabel, productLabel, relationshipCount, relationships, riskReport, summary]);

  const selected = nodes.find((node) => node.id === selectedId) ?? nodes[0];
  const graphTransform = `translate(350 225) scale(${zoom}) translate(-350 -225)`;

  function selectNode(id: string) {
    setSelectedId(id);
  }

  function handleNodeKeyDown(event: KeyboardEvent<SVGGElement>, id: string) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectNode(id);
    }
  }

  function updateZoom(next: number) {
    setZoom(Math.min(2.2, Math.max(0.7, Number(next.toFixed(2)))));
  }

  return (
    <article className="hcs-template-graph-panel">
      <div className="section-heading">
        <h3>
          <span className="hcs-pulse-dot" />
          HCS Dual-Core Architecture / 组织资产与意志行动双星系拓扑
        </h3>
        <span>通用标准拓扑图架</span>
      </div>
      <div className="hcs-template-toolbar" aria-label="图谱缩放控制">
        <button type="button" className="secondary-button graph-tool-btn" onClick={() => updateZoom(zoom + 0.15)}>放大</button>
        <button type="button" className="secondary-button graph-tool-btn" onClick={() => updateZoom(zoom - 0.15)}>缩小</button>
        <button type="button" className="secondary-button graph-tool-btn" onClick={() => updateZoom(1)}>重置</button>
        <span>{Math.round(zoom * 100)}%</span>
      </div>
      <div
        className="hcs-template-graph-canvas"
        onWheel={(event) => {
          event.preventDefault();
          updateZoom(zoom + (event.deltaY < 0 ? 0.08 : -0.08));
        }}
      >
        <svg className="hcs-template-svg" viewBox="0 0 700 450" role="img" aria-label="HCS 双核心标准拓扑">
          <defs>
            <marker id="hcs-arrow-green" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#10b981" />
            </marker>
            <marker id="hcs-arrow-red" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#f43f5e" />
            </marker>
            <marker id="hcs-arrow-cyan" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#06b6d4" />
            </marker>
          </defs>

          <g transform={graphTransform}>
            <line x1="220" y1="225" x2="480" y2="225" stroke="#06b6d4" strokeWidth="2" markerEnd="url(#hcs-arrow-cyan)" />
            <text textAnchor="middle" x="350" y="215" fill="#0891b2" fontSize="8" fontFamily="monospace" fontWeight="700">
              [ 业务强关联: 询盘交互 / 流量锁线 ]
            </text>

            <line x1="220" y1="225" x2="220" y2="105" stroke="#f43f5e" strokeWidth="1.5" strokeDasharray="4,4" markerEnd="url(#hcs-arrow-red)" />
            <line x1="220" y1="225" x2="85" y2="135" stroke="#d97706" strokeWidth="1" strokeDasharray="3,3" />
            <line x1="220" y1="225" x2="75" y2="225" stroke="#10b981" strokeWidth="1.2" markerEnd="url(#hcs-arrow-green)" />
            <line x1="220" y1="225" x2="100" y2="315" stroke="#10b981" strokeWidth="1.2" markerEnd="url(#hcs-arrow-green)" />
            <line x1="220" y1="225" x2="220" y2="345" stroke="#10b981" strokeWidth="2" markerEnd="url(#hcs-arrow-green)" />

            <g className={`hcs-click-node ${selectedId === "organization-core" ? "is-selected" : ""}`} transform="translate(220,225)" role="button" tabIndex={0} onClick={() => selectNode("organization-core")} onKeyDown={(event) => handleNodeKeyDown(event, "organization-core")}>
              <circle r="32" fill="#eff6ff" stroke="#2563eb" strokeWidth="2.5" />
              <text textAnchor="middle" y="-4" fill="#1e3a8a" fontSize="9" fontWeight="700">【组织资产核】</text>
              <text textAnchor="middle" y="8" fill="#2563eb" fontSize="8" fontFamily="monospace" fontWeight="700">{nodes.find((node) => node.id === "organization-core")?.subtitle}</text>
              <text textAnchor="middle" y="17" fill="#64748b" fontSize="6">Enterprise Asset Hub</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "offshore-shell" ? "is-selected" : ""}`} transform="translate(220,85)" role="button" tabIndex={0} onClick={() => selectNode("offshore-shell")} onKeyDown={(event) => handleNodeKeyDown(event, "offshore-shell")}>
              <rect x="-65" y="-14" width="130" height="28" rx="4" fill="#fff1f2" stroke="#f43f5e" strokeWidth="1.5" />
              <text textAnchor="middle" y="3" fill="#991b1b" fontSize="8" fontWeight="700">{nodes.find((node) => node.id === "offshore-shell")?.subtitle.slice(0, 18)}</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "manufacturing-base" ? "is-selected" : ""}`} transform="translate(85,115)" role="button" tabIndex={0} onClick={() => selectNode("manufacturing-base")} onKeyDown={(event) => handleNodeKeyDown(event, "manufacturing-base")}>
              <rect x="-55" y="-14" width="110" height="28" rx="14" fill="#fffbeb" stroke="#d97706" strokeWidth="1" strokeDasharray="2,2" />
              <text textAnchor="middle" y="3" fill="#92400e" fontSize="8">{nodes.find((node) => node.id === "manufacturing-base")?.subtitle.slice(0, 16)}</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "product-line" ? "is-selected" : ""}`} transform="translate(55,225)" role="button" tabIndex={0} onClick={() => selectNode("product-line")} onKeyDown={(event) => handleNodeKeyDown(event, "product-line")}>
              <rect x="-45" y="-20" width="90" height="32" rx="4" fill="#f0fdf4" stroke="#16a34a" strokeWidth="1" />
              <text textAnchor="middle" y="-4" fill="#14532d" fontSize="8" fontWeight="700">[核心主营产品线]</text>
              <text textAnchor="middle" y="7" fill="#166534" fontSize="6">{nodes.find((node) => node.id === "product-line")?.subtitle.slice(0, 18)}</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "digital-footprint" ? "is-selected" : ""}`} transform="translate(100,330)" role="button" tabIndex={0} onClick={() => selectNode("digital-footprint")} onKeyDown={(event) => handleNodeKeyDown(event, "digital-footprint")}>
              <rect x="-55" y="-18" width="110" height="30" rx="4" fill="#f0fdf4" stroke="#16a34a" strokeWidth="1" />
              <text textAnchor="middle" y="-3" fill="#14532d" fontSize="8" fontWeight="700">[数字踪迹/代运营网络]</text>
              <text textAnchor="middle" y="7" fill="#0891b2" fontSize="7">{nodes.find((node) => node.id === "digital-footprint")?.subtitle.slice(0, 20)}</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "landed-entity" ? "is-selected" : ""}`} transform="translate(220,375)" role="button" tabIndex={0} onClick={() => selectNode("landed-entity")} onKeyDown={(event) => handleNodeKeyDown(event, "landed-entity")}>
              <rect x="-70" y="-18" width="140" height="34" rx="4" fill="#f8fafc" stroke="#475569" strokeWidth="1.5" />
              <text textAnchor="middle" y="-3" fill="#0f172a" fontSize="9" fontWeight="700">穿透落地经营实体名称</text>
              <text textAnchor="middle" y="7" fill="#475569" fontSize="7">{nodes.find((node) => node.id === "landed-entity")?.subtitle.slice(0, 22)}</text>
            </g>

            <line x1="480" y1="225" x2="480" y2="125" stroke="#94a3b8" strokeWidth="1" strokeDasharray="2,2" />
            <line x1="480" y1="225" x2="600" y2="155" stroke="#94a3b8" strokeWidth="1" strokeDasharray="2,2" />
            <line x1="480" y1="225" x2="610" y2="225" stroke="#10b981" strokeWidth="1.2" markerEnd="url(#hcs-arrow-green)" />
            <line x1="480" y1="225" x2="590" y2="305" stroke="#94a3b8" strokeWidth="1" strokeDasharray="2,2" />

            <g className={`hcs-click-node ${selectedId === "decision-core" ? "is-selected" : ""}`} transform="translate(480,225)" role="button" tabIndex={0} onClick={() => selectNode("decision-core")} onKeyDown={(event) => handleNodeKeyDown(event, "decision-core")}>
              <circle r="32" fill="#ecfdf5" stroke="#10b981" strokeWidth="2.5" />
              <text textAnchor="middle" y="-4" fill="#064e3b" fontSize="9" fontWeight="700">【意志决策核】</text>
              <text textAnchor="middle" y="8" fill="#10b981" fontSize="8" fontFamily="monospace" fontWeight="700">{nodes.find((node) => node.id === "decision-core")?.subtitle}</text>
              <text textAnchor="middle" y="17" fill="#047857" fontSize="6">Action & Intention Core</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "persona-role" ? "is-selected" : ""}`} transform="translate(480,105)" role="button" tabIndex={0} onClick={() => selectNode("persona-role")} onKeyDown={(event) => handleNodeKeyDown(event, "persona-role")}>
              <rect x="-55" y="-14" width="110" height="28" rx="4" fill="#ffffff" stroke="#cbd5e1" strokeWidth="1" strokeDasharray="3,3" />
              <text textAnchor="middle" y="3" fill="#94a3b8" fontSize="8">{nodes.find((node) => node.id === "persona-role")?.subtitle.slice(0, 16)}</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "contact-channel" ? "is-selected" : ""}`} transform="translate(615,145)" role="button" tabIndex={0} onClick={() => selectNode("contact-channel")} onKeyDown={(event) => handleNodeKeyDown(event, "contact-channel")}>
              <rect x="-55" y="-14" width="110" height="28" rx="4" fill="#ffffff" stroke="#cbd5e1" strokeWidth="1" strokeDasharray="3,3" />
              <text textAnchor="middle" y="3" fill="#94a3b8" fontSize="8">{nodes.find((node) => node.id === "contact-channel")?.subtitle.slice(0, 22)}</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "location" ? "is-selected" : ""}`} transform="translate(625,225)" role="button" tabIndex={0} onClick={() => selectNode("location")} onKeyDown={(event) => handleNodeKeyDown(event, "location")}>
              <rect x="-45" y="-16" width="90" height="32" rx="4" fill="#ecfdf5" stroke="#10b981" strokeWidth="1" />
              <text textAnchor="middle" y="-2" fill="#047857" fontSize="9" fontWeight="700">{nodes.find((node) => node.id === "location")?.subtitle.slice(0, 14)}</text>
              <text textAnchor="middle" y="8" fill="#059669" fontSize="7">本地时区 / 常驻地</text>
            </g>
            <g className={`hcs-click-node ${selectedId === "activity-habit" ? "is-selected" : ""}`} transform="translate(605,320)" role="button" tabIndex={0} onClick={() => selectNode("activity-habit")} onKeyDown={(event) => handleNodeKeyDown(event, "activity-habit")}>
              <rect x="-55" y="-14" width="110" height="28" rx="4" fill="#ffffff" stroke="#cbd5e1" strokeWidth="1" strokeDasharray="3,3" />
              <text textAnchor="middle" y="3" fill="#94a3b8" fontSize="8">{nodes.find((node) => node.id === "activity-habit")?.subtitle.slice(0, 18)}</text>
            </g>
          </g>
        </svg>
        <aside className={`hcs-node-detail hcs-node-detail-${selected.tone}`}>
          <span>节点详情</span>
          <h4>{selected.title}</h4>
          <strong>{selected.subtitle}</strong>
          <p>{selected.body}</p>
          {selected.items?.length ? (
            <ul>
              {selected.items.slice(0, 4).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </aside>
        <div className="hcs-template-graph-note">
          <span>● 双核架构:</span> 组织资产核（左）提供硬资产闭环 · 意志决策核（右）提供行动路径刺探
        </div>
      </div>
    </article>
  );
}
