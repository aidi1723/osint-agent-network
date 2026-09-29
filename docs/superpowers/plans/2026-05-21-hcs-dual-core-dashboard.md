# HCS Dual Core Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the selected investigation data board into a light HCS dual-core intelligence cockpit while preserving the existing task-center workflow and backend contracts.

**Architecture:** Keep the existing React/Vite app and component set. Add a small metrics helper, reshape the selected-investigation JSX in `src/main.tsx`, and express the reference visual system through reusable CSS classes in `src/styles.css`. Preserve existing graph behavior and restyle the graph wrapper/canvas through class changes.

**Tech Stack:** React 19, TypeScript, Vite, CSS, lucide-react, existing API payloads.

---

## File Map

- Modify: `frontend/src/main.tsx`
  - Replace the selected `data-board` layout with HCS cockpit sections.
  - Derive cockpit metrics from existing `selected` data.
  - Keep all existing fetch, action, queue, and selection behavior.
- Modify: `frontend/src/styles.css`
  - Add HCS light grid, cockpit panels, intelligence bar, BLUF block, three-column grid, lower assessment zone, compact evidence cards, pipeline rows, and graph visual refinements.
  - Preserve existing generic panel, table, form, and status behavior.
- Create: `frontend/src/dashboard-metrics.ts`
  - Export pure helpers for selected-dashboard metric values, including gap display.
- Create: `frontend/src/dashboard-metrics.test.ts`
  - Test helper behavior with no selected investigation, populated selected data, null confidence, and graph collection gaps.

## Task 1: Add Cockpit Metric Helpers

**Files:**
- Create: `frontend/src/dashboard-metrics.ts`
- Create: `frontend/src/dashboard-metrics.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/dashboard-metrics.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { buildCockpitMetrics, cockpitBluf } from "./dashboard-metrics";
import type { Investigation } from "./types";

function investigation(overrides: Partial<Investigation> = {}): Investigation {
  return {
    id: "inv-1",
    name: "example.com 深度调查",
    seed_type: "domain",
    seed_value: "example.com",
    strategy: "deep",
    status: "COMPLETED",
    claimed_by_agent_id: null,
    claimed_by_agent_name: null,
    claimed_at: null,
    claim_expires_at: null,
    completed_at: null,
    archived_at: null,
    confidence: 0.82,
    summary: "BLUF: 主体与数字足迹存在明显冲突。",
    entities: [{ id: "e1" } as Investigation["entities"][number]],
    facts: [{ id: "f1" } as Investigation["facts"][number], { id: "f2" } as Investigation["facts"][number]],
    evidence: [],
    evidence_ledger: [
      { id: "l1" } as Investigation["evidence_ledger"][number],
      { id: "l2" } as Investigation["evidence_ledger"][number],
      { id: "l3" } as Investigation["evidence_ledger"][number],
    ],
    relationships: [{ id: "r1" } as Investigation["relationships"][number]],
    hypotheses: [],
    jobs: [],
    job_counts: {},
    graph: {
      nodes: [],
      edges: [],
      summary: {
        nodes: 0,
        edges: 0,
        evidence_nodes: 0,
        source_nodes: 0,
        entity_nodes: 0,
        risk_nodes: 0,
        collection_gaps: 4,
        memory_findings: 0,
      },
    },
    ...overrides,
  };
}

describe("dashboard metrics", () => {
  it("returns placeholder metrics when no investigation is selected", () => {
    expect(buildCockpitMetrics(null)).toEqual([
      { label: "综合置信度", value: "-" },
      { label: "证据账本", value: "0" },
      { label: "事实池", value: "0" },
      { label: "缺口", value: "-" },
    ]);
  });

  it("derives compact metrics from selected investigation data", () => {
    expect(buildCockpitMetrics(investigation())).toEqual([
      { label: "综合置信度", value: "0.82", tone: "success" },
      { label: "证据账本", value: "3" },
      { label: "事实池", value: "2" },
      { label: "缺口", value: "4", tone: "warning" },
    ]);
  });

  it("uses a dash for null confidence and missing graph gaps", () => {
    expect(buildCockpitMetrics(investigation({ confidence: null, graph: undefined })).toEqual([
      { label: "综合置信度", value: "-" },
      { label: "证据账本", value: "3" },
      { label: "事实池", value: "2" },
      { label: "缺口", value: "-" },
    ]);
  });

  it("uses selected summary as BLUF and falls back to waiting copy", () => {
    expect(cockpitBluf(investigation())).toBe("BLUF: 主体与数字足迹存在明显冲突。");
    expect(cockpitBluf(investigation({ summary: "" }))).toBe("Agent 完成任务后会在这里回写摘要、实体、证据和关系。");
  });
});
```

- [ ] **Step 2: Add the missing test dependency if needed**

Run:

```bash
npm install -D vitest
```

Expected: `package.json` gains `vitest` under `devDependencies`.

- [ ] **Step 3: Add a test script**

Modify `frontend/package.json` scripts to include:

```json
"test": "vitest run"
```

Expected script block:

```json
"scripts": {
  "dev": "vite --host 0.0.0.0 --port 3008",
  "build": "tsc && vite build",
  "check:ui-copy": "node scripts/check-chinese-ui.mjs",
  "preview": "vite preview --host 0.0.0.0 --port 3008",
  "test": "vitest run"
}
```

- [ ] **Step 4: Run test to verify it fails**

Run:

```bash
npm test -- dashboard-metrics.test.ts
```

Expected: FAIL because `./dashboard-metrics` does not exist.

- [ ] **Step 5: Implement the helper**

Create `frontend/src/dashboard-metrics.ts`:

```ts
import type { Investigation } from "./types";

export type CockpitMetric = {
  label: string;
  value: string;
  tone?: "success" | "warning" | "danger";
};

export function cockpitBluf(selected: Investigation | null) {
  return selected?.summary?.trim() || "Agent 完成任务后会在这里回写摘要、实体、证据和关系。";
}

export function buildCockpitMetrics(selected: Investigation | null): CockpitMetric[] {
  if (!selected) {
    return [
      { label: "综合置信度", value: "-" },
      { label: "证据账本", value: "0" },
      { label: "事实池", value: "0" },
      { label: "缺口", value: "-" },
    ];
  }

  const gapCount = selected.graph?.summary.collection_gaps;

  return [
    {
      label: "综合置信度",
      value: selected.confidence === null ? "-" : selected.confidence.toFixed(2),
      tone: selected.confidence === null ? undefined : "success",
    },
    { label: "证据账本", value: String(selected.evidence_ledger?.length ?? 0) },
    { label: "事实池", value: String(selected.facts?.length ?? 0) },
    {
      label: "缺口",
      value: typeof gapCount === "number" ? String(gapCount) : "-",
      tone: typeof gapCount === "number" && gapCount > 0 ? "warning" : undefined,
    },
  ];
}
```

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
npm test -- dashboard-metrics.test.ts
```

Expected: PASS.

## Task 2: Build The HCS Cockpit JSX

**Files:**
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Import the metrics helper**

Add near existing imports:

```ts
import { buildCockpitMetrics, cockpitBluf } from "./dashboard-metrics";
```

- [ ] **Step 2: Derive cockpit values**

After `selectedMetrics`, add:

```ts
  const cockpitMetrics = buildCockpitMetrics(selected);
  const selectedBluf = cockpitBluf(selected);
```

- [ ] **Step 3: Replace the selected data-board heading**

Replace the current `panel-heading board-heading` block inside `<section className="panel data-board" ref={dataBoardRef}>` with:

```tsx
          <div className="hcs-intel-bar">
            <div className="hcs-core-mark" aria-hidden="true">
              <span>CORE</span>
              <strong>02</strong>
            </div>
            <div className="hcs-intel-title">
              <div className="hcs-kicker-row">
                <span className="hcs-kicker">DUAL-CORE STANDARD</span>
                {selected ? <span className={statusClass(selected.status)}>{labelOf(taskStateLabels, selected.status)}</span> : null}
              </div>
              <h2>{selected ? selected.name : "HCS 双核心情报控制舱"}</h2>
              <code>{selected ? `${labelOf(targetTypeLabels, selected.seed_type)}: ${selected.seed_value}` : "选择任务后载入组织资产核与意志决策核"}</code>
            </div>
            <div className="hcs-bluf">
              <span>BLUF</span>
              <p>{selectedBluf}</p>
            </div>
            <div className="hcs-metric-strip">
              {cockpitMetrics.map((metric) => (
                <div key={metric.label} className={`hcs-metric${metric.tone ? ` hcs-metric-${metric.tone}` : ""}`}>
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
          </div>
```

- [ ] **Step 4: Replace the selected board body layout**

Inside `{selected ? (...) : (...)}`, replace the current three `board-column` sections with this structure:

```tsx
            <div className={`hcs-cockpit${loadingDetail ? " detail-loading" : ""}`}>
              <section className="hcs-column hcs-left-rail">
                <EvidenceLedgerPanel evidenceLedger={selected.evidence_ledger} />
                <FactPoolPanel facts={selected.facts} evidenceLedger={selected.evidence_ledger} />
              </section>
              <section className="hcs-column hcs-graph-core">
                <RelationshipGraphPanel graph={selected.combined_graph ?? selected.graph} />
              </section>
              <section className="hcs-column hcs-right-rail">
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
              </section>
              <section className="hcs-assessment">
                <article className="report-card hcs-whitepaper">
                  <h3>皇城司双核协同情报评估白皮书</h3>
                  <div className="report-markdown" dangerouslySetInnerHTML={selected.report_markdown ? { __html: marked.parse(selected.report_markdown) as string } : undefined}>
                    {!selected.report_markdown ? <p>暂无正文报告。事实池、证据账本、ACH 假说和情报记忆已经作为下一轮报告与 agent 接力的结构化底座。</p> : null}
                  </div>
                </article>
                <div className="hcs-gap-stack">
                  <ReportAuditPanel
                    facts={selected.facts}
                    evidenceLedger={selected.evidence_ledger}
                    hypotheses={selected.hypotheses}
                    analysis={selected.hypothesis_analysis}
                    memory={selected.intelligence_memory}
                    reportMarkdown={selected.report_markdown}
                  />
                  <IntelligenceMemoryPanel memory={selected.intelligence_memory} />
                </div>
              </section>
              <section className="hcs-overflow-data">
                <MiniMetrics metrics={selectedMetrics} />
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
              </section>
            </div>
```

- [ ] **Step 5: Remove duplicated old report/list JSX**

Delete the old duplicated `summary-line`, `stage-strip`, `QueuePanel`, `DecisionProfilePanel`, `RiskReviewPanel`, `IntelligenceMemoryPanel`, `ReportAuditPanel`, `MiniMetrics`, report card, `FactPoolPanel`, `EvidenceLedgerPanel`, `HypothesisPanel`, entities, evidence, and relationships blocks that were part of the previous `board-layout` columns.

- [ ] **Step 6: Preserve sparse-lead stage strip**

Inside the new `.hcs-intel-title` block after the `<code>` line, add:

```tsx
              {selected && isSparseLeadInvestigation(selected.seed_type) ? (
                <div className="stage-strip hcs-stage-strip">
                  {sparseLeadStages(selected.jobs ?? []).map((stage) => (
                    <span key={stage.key} className={`stage-chip stage-${stage.status.toLowerCase()}`}>
                      {stage.label}
                    </span>
                  ))}
                </div>
              ) : null}
```

- [ ] **Step 7: Run TypeScript build to catch JSX/type errors**

Run:

```bash
npm run build
```

Expected: Any errors are limited to styling not yet implemented only if class names are unused; TypeScript should pass. If TypeScript fails, fix the exact referenced lines before continuing.

## Task 3: Add HCS Visual System CSS

**Files:**
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add design tokens**

At the top of `:root`, add:

```css
  --hcs-bg: #f8fafc;
  --hcs-surface: #ffffff;
  --hcs-soft: #f1f5f9;
  --hcs-border: #e2e8f0;
  --hcs-border-strong: #cbd5e1;
  --hcs-text: #0f172a;
  --hcs-muted: #64748b;
  --hcs-blue: #2563eb;
  --hcs-green: #10b981;
  --hcs-cyan: #06b6d4;
  --hcs-amber: #d97706;
  --hcs-rose: #f43f5e;
```

- [ ] **Step 2: Add the background grid**

Update `body`:

```css
body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background:
    linear-gradient(to right, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    var(--hcs-bg);
  background-size: 30px 30px;
}
```

- [ ] **Step 3: Add cockpit header and metric styles**

Append:

```css
.hcs-intel-bar {
  display: grid;
  grid-template-columns: auto minmax(220px, 1.2fr) minmax(280px, 2fr) minmax(300px, 1fr);
  gap: 12px;
  align-items: stretch;
  border: 1px solid var(--hcs-border);
  background: rgba(255, 255, 255, 0.94);
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.05);
}

.hcs-core-mark {
  width: 54px;
  min-height: 54px;
  border: 1px solid var(--hcs-border-strong);
  border-radius: 8px;
  background: var(--hcs-soft);
  display: grid;
  place-items: center;
  align-content: center;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

.hcs-core-mark span,
.hcs-kicker,
.hcs-bluf span,
.hcs-metric span {
  color: var(--hcs-muted);
  font-size: 10px;
}

.hcs-core-mark strong {
  color: var(--hcs-text);
  font-size: 18px;
  line-height: 1;
}

.hcs-intel-title {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.hcs-kicker-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.hcs-kicker {
  width: fit-content;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 4px;
  padding: 2px 6px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-weight: 700;
}

.hcs-intel-title h2 {
  color: var(--hcs-text);
  font-size: 16px;
  line-height: 1.25;
}

.hcs-intel-title code {
  color: var(--hcs-muted);
  overflow-wrap: anywhere;
}

.hcs-stage-strip {
  margin: 2px 0 0;
}

.hcs-bluf {
  position: relative;
  border: 1px solid var(--hcs-border);
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 12px;
  min-width: 0;
}

.hcs-bluf span {
  position: absolute;
  top: 0;
  right: 0;
  border-left: 1px solid #fecdd3;
  border-bottom: 1px solid #fecdd3;
  border-radius: 0 8px 0 6px;
  background: #ffe4e6;
  color: #be123c;
  padding: 2px 8px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-weight: 700;
}

.hcs-bluf p {
  color: #475569;
  font-size: 12px;
  line-height: 1.55;
  padding-right: 44px;
}

.hcs-metric-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.hcs-metric {
  border: 1px solid var(--hcs-border);
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px 10px;
  text-align: center;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

.hcs-metric strong {
  display: block;
  color: var(--hcs-text);
  font-size: 16px;
  margin-top: 3px;
}

.hcs-metric-success strong {
  color: #059669;
}

.hcs-metric-warning strong {
  color: var(--hcs-amber);
}

.hcs-metric-danger strong {
  color: var(--hcs-rose);
}
```

- [ ] **Step 4: Add cockpit grid and panel styles**

Append:

```css
.hcs-cockpit {
  display: grid;
  grid-template-columns: minmax(260px, 3fr) minmax(460px, 6fr) minmax(280px, 3fr);
  gap: 14px;
  align-items: start;
}

.hcs-column {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.hcs-graph-core {
  min-height: 560px;
}

.core-v2-panel,
.review-panel,
.report-card,
.hcs-agent-pipeline {
  border: 1px solid var(--hcs-border);
  background: rgba(255, 255, 255, 0.96);
  border-radius: 8px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
}

.core-v2-panel,
.review-panel,
.hcs-agent-pipeline {
  padding: 12px;
}

.section-heading {
  border-bottom: 1px solid #eef2f7;
  padding-bottom: 8px;
  margin-bottom: 10px;
}

.section-heading h3 {
  margin: 0;
  color: #334155;
  font-size: 12px;
  text-transform: uppercase;
}

.data-row {
  border-left: 3px solid var(--hcs-border-strong);
  background: #f8fafc;
}

.data-row:nth-child(4n + 1) {
  border-left-color: var(--hcs-green);
}

.data-row:nth-child(4n + 2) {
  border-left-color: var(--hcs-rose);
}

.data-row:nth-child(4n + 3) {
  border-left-color: var(--hcs-amber);
}

.data-row:nth-child(4n + 4) {
  border-left-color: var(--hcs-cyan);
}
```

- [ ] **Step 5: Add lower assessment and pipeline styles**

Append:

```css
.hcs-assessment {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
  gap: 14px;
}

.hcs-whitepaper {
  padding: 16px;
}

.hcs-whitepaper h3 {
  margin: 0 0 12px;
  color: var(--hcs-text);
  font-size: 15px;
}

.hcs-gap-stack,
.hcs-overflow-data {
  display: grid;
  gap: 12px;
}

.hcs-overflow-data {
  grid-column: 1 / -1;
}

.hcs-overflow-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.hcs-pipeline-list {
  display: grid;
  gap: 8px;
}

.hcs-pipeline-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  border: 1px solid var(--hcs-border);
  background: #f8fafc;
  border-radius: 8px;
  padding: 8px;
}

.hcs-pipeline-row strong,
.hcs-pipeline-row span {
  display: block;
}

.hcs-pipeline-row span {
  color: var(--hcs-muted);
  font-size: 11px;
}

.hcs-pipeline-row em {
  color: #059669;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
}
```

- [ ] **Step 6: Add responsive rules**

Append:

```css
@media (max-width: 1280px) {
  .hcs-intel-bar {
    grid-template-columns: auto minmax(220px, 1fr) minmax(260px, 1.4fr);
  }

  .hcs-metric-strip {
    grid-column: 1 / -1;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .hcs-cockpit {
    grid-template-columns: minmax(280px, 1fr) minmax(420px, 1.45fr);
  }

  .hcs-right-rail {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .hcs-intel-bar,
  .hcs-cockpit,
  .hcs-assessment,
  .hcs-overflow-grid,
  .hcs-right-rail {
    grid-template-columns: 1fr;
  }

  .hcs-metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .hcs-intel-bar {
    padding: 10px;
  }

  .hcs-metric-strip {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 7: Run build after CSS changes**

Run:

```bash
npm run build
```

Expected: PASS.

## Task 4: Restyle The Graph As HCS K-GRAPH

**Files:**
- Modify: `frontend/src/components/GraphPanel.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Rename visible graph heading**

In `RelationshipGraphPanel`, change both graph headings:

```tsx
<div className="section-heading"><h3>HCS K-GRAPH / 双轴协同验证拓扑</h3><span>未生成</span></div>
```

and:

```tsx
<h3>HCS K-GRAPH / 双轴协同验证拓扑</h3>
```

- [ ] **Step 2: Add a dual-core annotation below the canvas**

After the `.graph-canvas` div and before `.graph-footer`, add:

```tsx
      <div className="hcs-graph-note">
        <span>● 双核架构:</span> 组织资产核提供硬资产闭环，意志决策核提供行动路径刺探。
      </div>
```

- [ ] **Step 3: Add graph visual CSS**

Append to `frontend/src/styles.css`:

```css
.graph-panel {
  overflow: hidden;
}

.graph-canvas {
  border: 1px solid var(--hcs-border);
  border-radius: 8px;
  background:
    linear-gradient(to right, rgba(148, 163, 184, 0.1) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(148, 163, 184, 0.1) 1px, transparent 1px),
    #f8fafc;
  background-size: 24px 24px;
  min-height: 470px;
  box-shadow: inset 0 1px 8px rgba(15, 23, 42, 0.04);
}

.hcs-graph-note {
  border: 1px solid var(--hcs-border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.94);
  color: var(--hcs-muted);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  line-height: 1.45;
  margin-top: 8px;
  padding: 7px 9px;
}

.hcs-graph-note span {
  color: #0891b2;
  font-weight: 700;
}

.graph-zones .zone {
  fill: rgba(248, 250, 252, 0.72);
  stroke: rgba(148, 163, 184, 0.42);
}

.graph-zones .zone-slot {
  fill: rgba(255, 255, 255, 0.72);
  stroke: rgba(203, 213, 225, 0.76);
}
```

- [ ] **Step 4: Run build**

Run:

```bash
npm run build
```

Expected: PASS.

## Task 5: Browser Verification And Final Polish

**Files:**
- Modify: `frontend/src/styles.css` only if visual bugs are found.
- Modify: `frontend/src/main.tsx` only if structure bugs are found.

- [ ] **Step 1: Run full local verification**

Run:

```bash
npm test
npm run check:ui-copy
npm run build
```

Expected:
- `npm test`: PASS.
- `npm run check:ui-copy`: PASS or a clear pre-existing/project-specific failure that must be reported.
- `npm run build`: PASS.

- [ ] **Step 2: Start the dev server**

Run:

```bash
npm run dev
```

Expected: Vite serves at `http://localhost:3008/`.

- [ ] **Step 3: Inspect desktop in browser**

Open `http://localhost:3008/` in the in-app browser. Select a task if one is present. Verify:

- No selected state still displays the empty prompt.
- Selected state shows the HCS intelligence bar.
- Three cockpit columns render without overlapping text.
- Graph canvas is nonblank when graph data exists.
- Run queue and task action controls remain clickable.

- [ ] **Step 4: Inspect mobile/tablet responsiveness**

Use browser viewport checks around 390px and 900px widths. Verify:

- Header metrics wrap cleanly.
- Cockpit sections stack in readable order.
- Tables and long code strings do not overflow their containers.
- Buttons wrap without text clipping.

- [ ] **Step 5: Fix observed visual defects**

If text overlaps, add the specific fix:

```css
.hcs-intel-title,
.hcs-bluf,
.hcs-column,
.hcs-overflow-grid > * {
  min-width: 0;
}

.hcs-intel-title code,
.data-row code,
.report-markdown {
  overflow-wrap: anywhere;
}
```

If graph height collapses, add:

```css
.hcs-graph-core .graph-panel {
  min-height: 560px;
}
```

- [ ] **Step 6: Re-run verification after any fix**

Run:

```bash
npm test
npm run build
```

Expected: PASS.

## Self-Review Checklist

- Spec coverage:
  - HCS intelligence bar: Task 2 and Task 3.
  - Three-column cockpit: Task 2 and Task 3.
  - Graph preservation and restyle: Task 4.
  - Lower assessment zone: Task 2 and Task 3.
  - No backend changes: all tasks stay frontend-only.
  - Responsive and accessibility checks: Task 3 and Task 5.
- Placeholder scan: no `TBD`, `TODO`, `implement later`, or unspecified test steps.
- Type consistency: helper exports `buildCockpitMetrics` and `cockpitBluf`; `main.tsx` imports those exact names.
