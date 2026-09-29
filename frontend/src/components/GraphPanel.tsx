import React, { useMemo, useRef, useState, useCallback } from "react";
import {
  curvedEdgePath,
  edgeEndpoints,
  edgeLabelPoint,
  edgeStrokeWidth,
  edgeTone,
  graphDisplayNodes,
  graphTemplateSlots,
  graphVisibleEdges,
  layoutEvidenceMap,
  shouldShowEdgeLabel,
  nodeVisualGroup,
  type GraphEdge,
  type GraphLayout,
  type GraphNode,
  type GraphPoint,
} from "../graph";
import {
  labelOf,
  graphNodeTypeLabels,
  entityTypeLabels,
  evidenceKindLabels,
  targetTypeLabels,
  sourceKindLabels,
  graphEdgeTypeLabels,
  relationshipTypeLabels,
} from "../labels";
import type { InvestigationGraph } from "../types";
import { ZoomIn, ZoomOut, Maximize2 } from "lucide-react";

// ── helpers ──────────────────────────────────────────────────────────────────

function hashNumber(value: string) {
  let hash = 0;
  for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  return hash;
}

function truncateMiddle(value: string, limit: number) {
  if (value.length <= limit) return value;
  if (limit <= 5) return value.slice(0, limit);
  const head = Math.ceil((limit - 1) * 0.62);
  const tail = Math.floor((limit - 1) * 0.38);
  return `${value.slice(0, head)}…${value.slice(value.length - tail)}`;
}

function nodeMainLine(node: GraphNode) {
  return truncateMiddle(node.label || node.value || node.source_tool, ["evidence", "evidence_ledger", "fact", "hypothesis"].includes(node.type) ? 26 : 24);
}

function nodeMetaLine(node: GraphNode) {
  if (node.value === "待补充") return "待补充";
  if (node.type === "source") {
    const sk = typeof node.metadata.source_kind === "string" ? node.metadata.source_kind : "";
    return labelOf(sourceKindLabels, sk || "tool");
  }
  if (node.type === "evidence") {
    const ek = typeof node.metadata.evidence_kind === "string" ? node.metadata.evidence_kind : "evidence";
    return labelOf(evidenceKindLabels, ek);
  }
  if (node.type === "evidence_ledger") {
    const code = typeof node.metadata.admiralty_code === "string" ? node.metadata.admiralty_code : "";
    return code ? `账本 ${code}` : "证据账本";
  }
  if (node.type === "fact") {
    const status = typeof node.metadata.status === "string" ? node.metadata.status : "";
    return status || "事实池";
  }
  if (node.type === "hypothesis") {
    const status = typeof node.metadata.status === "string" ? node.metadata.status : "";
    return status || "假说池";
  }
  if (node.type === "risk_signal") return "人工复核";
  if (node.type === "seed") {
    const st = typeof node.metadata.seed_type === "string" ? node.metadata.seed_type : "seed";
    return labelOf(targetTypeLabels, st);
  }
  const conf = node.confidence ? `${Math.round(node.confidence * 100)}%` : "-";
  return `${node.source_tool || "来源未标注"} / ${conf}`;
}

function nodeSubtitle(node: GraphNode) {
  if (typeof node.metadata.template_label === "string") return node.metadata.template_label;
  if (node.type === "entity" && typeof node.metadata.entity_type === "string")
    return labelOf(entityTypeLabels, node.metadata.entity_type);
  if (node.type === "risk_signal") {
    const rl = typeof node.metadata.risk_level === "string" ? node.metadata.risk_level : node.risk_level || "low";
    return labelOf({ low: "低", medium: "中", high: "高", critical: "严重" }, rl);
  }
  return labelOf(graphNodeTypeLabels, node.type);
}

function edgeDisplayLabel(edge: GraphEdge) {
  if (edge.type === "source_emitted_entity" || edge.type === "source_emitted_evidence" || edge.type === "source_emitted_evidence_ledger") return "来源";
  if (edge.type === "supports_entity") return "证据";
  const label = labelOf(graphEdgeTypeLabels, edge.type);
  if (edge.confidence > 0 && !edge.type.includes("source") && !edge.type.includes("support"))
    return `${label} ${Math.round(edge.confidence * 100)}%`;
  return label;
}

function connectedGraphIds(edges: GraphEdge[], id: string | null) {
  const connected = new Set<string>();
  if (!id) return connected;
  connected.add(id);
  for (const edge of edges) {
    if (edge.id === id || edge.from === id || edge.to === id) {
      connected.add(edge.id);
      connected.add(edge.from);
      connected.add(edge.to);
    }
  }
  return connected;
}

function buildEvidenceChains(nodes: GraphNode[], edges: GraphEdge[]) {
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  return edges
    .filter((e) => e.type.includes("source") || e.type.includes("supports"))
    .map((edge) => {
      const from = nodeById.get(edge.from);
      const to = nodeById.get(edge.to);
      return {
        key: edge.id,
        source: from ? nodeMainLine(from) : edge.source || "来源未标注",
        bridge: edgeDisplayLabel(edge),
        target: to ? nodeMainLine(to) : "目标未解析",
        tone: edgeTone(edge, nodes),
      };
    });
}

// ── sub-components ────────────────────────────────────────────────────────────

function GraphZones({ layout }: { layout: GraphLayout }) {
  const slots = graphTemplateSlots();
  return (
    <g className="graph-zones" aria-hidden="true">
      <rect className="zone zone-evidence" x="85" y="36" width="1150" height="150" rx="8" />
      <rect className="zone zone-entity" x="190" y="215" width="940" height="540" rx="8" />
      <rect className="zone zone-evidence" x="85" y="820" width="1150" height="150" rx="8" />
      {slots.map((slot, i) =>
        slot.shape === "circle" ? (
          <circle key={i} className="zone-slot" cx={slot.x} cy={slot.y} r={slot.width / 2} />
        ) : (
          <rect key={i} className="zone-slot" x={slot.x - slot.width / 2} y={slot.y - slot.height / 2} width={slot.width} height={slot.height} rx="8" />
        ),
      )}
      <text x={layout.width / 2} y="66">证据</text>
      <text x="310" y="245">决策人画像</text>
      <text x="660" y="245">核心线索/上下游</text>
      <text x="1010" y="245">企业信息/触达</text>
      <text x={layout.width / 2} y="850">补充证据</text>
    </g>
  );
}

function GraphNodeDetail({ node }: { node: GraphNode }) {
  const entityType = typeof node.metadata.entity_type === "string" ? node.metadata.entity_type : node.type;
  const summary = typeof node.metadata.summary === "string" ? node.metadata.summary : "";
  const snippet = typeof node.metadata.snippet === "string" ? node.metadata.snippet : "";
  const sourceKind = typeof node.metadata.source_kind === "string" ? node.metadata.source_kind : "";
  return (
    <div className="graph-node-detail">
      <div>
        <strong>{node.label}</strong>
        <span>{labelOf(graphNodeTypeLabels, node.type)} / {labelOf(entityTypeLabels, entityType)}</span>
      </div>
      <code>{node.value || summary || snippet || node.source_tool}</code>
      <span>
        来源 {node.source_tool || "-"}{sourceKind ? ` / ${labelOf(sourceKindLabels, sourceKind)}` : ""} / 置信度 {node.confidence ? node.confidence.toFixed(2) : "-"} / 证据 {node.evidence_count}
      </span>
    </div>
  );
}

function OverflowList({ title, nodes }: { title: string; nodes: GraphNode[] }) {
  return (
    <div className="graph-overflow-list">
      <span>{title} · {nodes.length}</span>
      {nodes.slice(0, 8).map((node) => (
        <code key={node.id}>{nodeMainLine(node)}</code>
      ))}
      {nodes.length > 8 ? <strong>还有 {nodes.length - 8} 条</strong> : null}
      {!nodes.length ? <em>无</em> : null}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

type ViewTransform = { scale: number; tx: number; ty: number };

export function RelationshipGraphPanel({ graph }: { graph?: InvestigationGraph }) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [transform, setTransform] = useState<ViewTransform>({ scale: 1, tx: 0, ty: 0 });
  const isPanning = useRef(false);
  const panStart = useRef({ x: 0, y: 0, tx: 0, ty: 0 });

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];
  const displayNodes = useMemo(() => graphDisplayNodes(nodes), [nodes]);
  const displayNodeIds = useMemo(
    () => new Set(displayNodes.filter((n) => n.value !== "待补充").map((n) => n.id)),
    [displayNodes],
  );
  const displayEdges = useMemo(
    () => edges.filter((e) => displayNodeIds.has(e.from) && displayNodeIds.has(e.to)),
    [displayNodeIds, edges],
  );
  const layout = useMemo(() => layoutEvidenceMap(displayNodes, displayEdges), [displayEdges, displayNodes]);
  const visibleEdges = useMemo(() => graphVisibleEdges(displayEdges, displayNodes), [displayEdges, displayNodes]);
  const selectedNode = displayNodes.find((n) => n.id === selectedNodeId) ?? displayNodes[0] ?? null;
  const connectedIds = useMemo(() => connectedGraphIds(visibleEdges, hoveredId), [visibleEdges, hoveredId]);
  const evidenceChain = useMemo(() => buildEvidenceChains(nodes, edges), [edges, nodes]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.85 : 1.18;
    setTransform((prev) => ({ ...prev, scale: Math.min(4, Math.max(0.25, prev.scale * delta)) }));
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    isPanning.current = true;
    panStart.current = { x: e.clientX, y: e.clientY, tx: transform.tx, ty: transform.ty };
  }, [transform]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanning.current) return;
    setTransform((prev) => ({
      ...prev,
      tx: panStart.current.tx + (e.clientX - panStart.current.x),
      ty: panStart.current.ty + (e.clientY - panStart.current.y),
    }));
  }, []);

  const handleMouseUp = useCallback(() => { isPanning.current = false; }, []);

  function zoom(factor: number) {
    setTransform((prev) => ({ ...prev, scale: Math.min(4, Math.max(0.25, prev.scale * factor)) }));
  }

  if (!graph || nodes.length === 0) {
    return (
      <article className="review-panel graph-panel">
        <div className="section-heading"><h3>HCS K-GRAPH / 双轴协同验证拓扑</h3><span>未生成</span></div>
        <div className="empty compact">实体、证据或关系回写后，会在这里生成图谱。</div>
      </article>
    );
  }

  return (
    <article className="review-panel graph-panel">
      <div className="section-heading">
        <h3>HCS K-GRAPH / 双轴协同验证拓扑</h3>
        <span>主图 {displayNodes.length} 点 / {visibleEdges.length} 边 · 全量 {graph.summary.nodes} 点 / {graph.summary.edges} 边</span>
      </div>
      <div className="graph-summary">
        <span>中心 {displayNodes.filter((n) => n.type === "seed").length}</span>
        <span>实体 {displayNodes.filter((n) => n.type === "entity").length}</span>
        <span>证据 {displayNodes.filter((n) => ["evidence", "evidence_ledger", "fact", "hypothesis"].includes(n.type)).length}</span>
        <span>来源 {displayNodes.filter((n) => n.type === "source").length}</span>
        <span>风险 {displayNodes.filter((n) => n.type === "risk_signal").length}</span>
        <span>记忆 {graph.summary.memory_findings ?? 0}</span>
        <span>缺口 {graph.summary.collection_gaps ?? 0}</span>
      </div>
      <div className="graph-toolbar">
        <button type="button" className="secondary-button graph-tool-btn" onClick={() => zoom(1.25)} title="放大">
          <ZoomIn size={15} />
        </button>
        <button type="button" className="secondary-button graph-tool-btn" onClick={() => zoom(0.8)} title="缩小">
          <ZoomOut size={15} />
        </button>
        <button type="button" className="secondary-button graph-tool-btn" onClick={() => setTransform({ scale: 1, tx: 0, ty: 0 })} title="重置视图">
          <Maximize2 size={15} />
        </button>
        <span className="graph-zoom-label">{Math.round(transform.scale * 100)}%</span>
      </div>
      <div
        className="graph-canvas graph-canvas-interactive"
        role="img"
        aria-label="调查关系图谱"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg viewBox={`0 0 ${layout.width} ${layout.height}`} preserveAspectRatio="xMidYMid meet">
          <defs>
            <marker id="arrow-entity" markerWidth="18" markerHeight="12" refX="17" refY="6" orient="auto">
              <path d="M0,0 L0,12 L18,6 z" fill="#80b8d4" />
            </marker>
            <marker id="arrow-evidence" markerWidth="16" markerHeight="11" refX="15" refY="5.5" orient="auto">
              <path d="M0,0 L0,11 L16,5.5 z" fill="#9cb7c9" />
            </marker>
            <marker id="arrow-source" markerWidth="14" markerHeight="10" refX="13" refY="5" orient="auto">
              <path d="M0,0 L0,10 L14,5 z" fill="#d6ba64" />
            </marker>
            <marker id="arrow-risk" markerWidth="18" markerHeight="12" refX="17" refY="6" orient="auto">
              <path d="M0,0 L0,12 L18,6 z" fill="#e2a86b" />
            </marker>
            <marker id="arrow-default" markerWidth="16" markerHeight="11" refX="15" refY="5.5" orient="auto">
              <path d="M0,0 L0,11 L16,5.5 z" fill="#9aaaba" />
            </marker>
          </defs>
          <g transform={`translate(${transform.tx},${transform.ty}) scale(${transform.scale})`}>
            <GraphZones layout={layout} />
            {visibleEdges.map((edge) => {
              const from = layout.get(edge.from);
              const to = layout.get(edge.to);
              if (!from || !to) return null;
              const active = !hoveredId || connectedIds.has(edge.id) || connectedIds.has(edge.from) || connectedIds.has(edge.to);
              const tone = edgeTone(edge, displayNodes);
              const endpoints = edgeEndpoints(from, to);
              const mid = edgeLabelPoint(endpoints.from, endpoints.to, edge.id);
              const curve = curvedEdgePath(endpoints.from, endpoints.to, edge.id);
              return (
                <g key={edge.id} className={`graph-edge edge-${tone} ${active ? "active" : ""}`}
                  onMouseEnter={() => setHoveredId(edge.id)} onMouseLeave={() => setHoveredId(null)}>
                  <path d={curve} strokeWidth={edgeStrokeWidth(edge, tone)} markerEnd={`url(#arrow-${tone})`} />
                  {shouldShowEdgeLabel(edge) ? <text x={mid.x} y={mid.y - 5}>{edgeDisplayLabel(edge)}</text> : null}
                </g>
              );
            })}
            {displayNodes.map((node) => {
              const point = layout.get(node.id);
              if (!point) return null;
              const active = !hoveredId || connectedIds.has(node.id);
              const isEmpty = node.value === "待补充";
              return (
                <g key={node.id}
                  className={`graph-node node-${node.type} node-group-${nodeVisualGroup(node)} risk-${node.risk_level || "none"} ${isEmpty ? "node-empty" : ""} ${active ? "active" : "dimmed"}`}
                  transform={`translate(${point.x},${point.y})`}
                  onClick={() => { if (!isEmpty) setSelectedNodeId(node.id); }}
                  onMouseEnter={() => { if (!isEmpty) setHoveredId(node.id); }}
                  onMouseLeave={() => setHoveredId(null)}
                  onKeyDown={(e) => { if (!isEmpty && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setSelectedNodeId(node.id); } }}
                  role={isEmpty ? undefined : "button"} tabIndex={isEmpty ? undefined : 0}>
                  {point.shape === "circle"
                    ? <circle r={point.radius ?? 54} />
                    : <rect x={-(point.width / 2)} y={-(point.height / 2)} width={point.width} height={point.height} rx="8" />}
                  <text className="node-kicker" x="0" y={point.shape === "circle" ? -20 : -22}>{nodeSubtitle(node)}</text>
                  <text className="node-label" x="0" y={point.shape === "circle" ? -1 : -5}>{nodeMainLine(node)}</text>
                  <text className="node-meta" x="0" y={point.shape === "circle" ? 18 : 13}>{nodeMetaLine(node)}</text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <div className="hcs-graph-note">
        <span>● 双核架构:</span> 组织资产核提供硬资产闭环，意志决策核提供行动路径刺探。
      </div>
      <div className="graph-footer">
        <div className="graph-legend">
          <span><i className="legend-seed" />线索</span>
          <span><i className="legend-person" />人物/组织</span>
          <span><i className="legend-contact" />联系方式</span>
          <span><i className="legend-personal" />个人属性</span>
          <span><i className="legend-evidence" />公开证据</span>
          <span><i className="legend-source" />来源</span>
          <span><i className="legend-risk" />风险</span>
        </div>
        {selectedNode && !selectedNode.value.includes("待补充") ? <GraphNodeDetail node={selectedNode} /> : null}
      </div>
      <details className="source-chain-list">
        <summary>来源链 · {evidenceChain.length} 条</summary>
        {evidenceChain.slice(0, 5).map((item) => (
          <div key={item.key} className={`source-chain source-chain-${item.tone}`}>
            <code>{item.source}</code><span>{item.bridge}</span><strong>{item.target}</strong>
          </div>
        ))}
        {!evidenceChain.length ? <div className="empty compact">暂无来源链。</div> : null}
      </details>
      <details className="graph-overflow">
        <summary>折叠其余数据：{Math.max(0, nodes.length - displayNodes.length)} 个节点 / {Math.max(0, edges.length - visibleEdges.length)} 条关系</summary>
        <div className="graph-overflow-grid">
          <OverflowList title="其余实体" nodes={nodes.filter((n) => n.type === "entity" && !displayNodeIds.has(n.id))} />
          <OverflowList title="其余证据/事实" nodes={nodes.filter((n) => ["evidence", "evidence_ledger", "fact", "hypothesis"].includes(n.type) && !displayNodeIds.has(n.id))} />
          <OverflowList title="其余来源/风险" nodes={nodes.filter((n) => ["source", "risk_signal"].includes(n.type) && !displayNodeIds.has(n.id))} />
        </div>
      </details>
    </article>
  );
}
