# HCS Dual Core Dashboard Redesign

## Context

The current frontend is a React/Vite operations console for OSINT investigations. The existing `DESIGN.md` defines a dense, light, technical analyst workstation. The user provided a light "皇城司 (HCS) 双核心商业情报通用控制舱" reference and selected scope B: keep the current task-center workflow, but redesign the selected investigation data board into a dual-core control cockpit.

## Goals

- Preserve the existing task creation, agent status, task pool, API refresh, investigation actions, queue execution, graph interaction, and data contracts.
- Redesign only the selected investigation detail area into a high-density HCS dual-core dashboard.
- Translate the reference aesthetic into the existing app: light slate background, precise grid texture, white compact panels, mono tactical labels, blue/green dual-core emphasis, red/amber conflict and gap states.
- Make the selected investigation easier to scan by grouping evidence, graph, hypotheses, agent pipeline, report, and gaps into a cockpit layout.
- Keep the UI responsive and usable on tablet/mobile by collapsing the cockpit columns in source order.

## Non-Goals

- Do not replace the app with a landing page or marketing hero.
- Do not change backend endpoints, investigation models, graph data layout, task actions, or job execution behavior.
- Do not add a new component library.
- Do not create a full product-level navigation redesign.

## Recommended Implementation Base

Per `design-md-ui` and `framework-combination-map.md`, this is a source-owned React data-heavy admin product. The implementation should use the current React components and CSS, with shadcn-like token discipline expressed through project CSS variables and reusable panel classes. No external UI framework is needed.

## Visual System

### Color Roles

- Page background: `#f8fafc` with a subtle slate grid texture.
- Surface: `#ffffff`.
- Soft surface: `#f8fafc` and `#f1f5f9`.
- Border: `#e2e8f0`, with stronger separators at `#cbd5e1`.
- Primary dual-core blue: `#2563eb`.
- Decision/action green: `#10b981`.
- Link/flow cyan: `#06b6d4`.
- Warning amber: `#d97706`.
- Conflict red/rose: `#f43f5e`.
- Text: `#0f172a`, muted text `#64748b`.

### Typography

- Keep the existing system sans stack for UI labels and body.
- Use the existing monospace role for targets, codes, evidence hashes, state labels, and tactical headings.
- Dashboard headings should be compact: 12-16px, uppercase or mono where appropriate.
- No viewport-scaled text and no negative letter spacing.

### Surfaces

- Use 8px radius for panels and controls.
- Use 1px borders and restrained shadows.
- Cards remain individual repeated records, not nested section decoration.
- Grid texture belongs to the workspace/background and large graph canvas only.

## Cockpit Layout

### Header: HCS Intelligence Bar

Replace the simple `数据看板` heading for selected investigations with a compact cockpit header:

- Left block: `CORE 02`, `DUAL-CORE STANDARD`, selected investigation name, seed type/value, and current status.
- Center BLUF block: use `selected.summary` when present. When missing, show the current waiting copy that explains agent回写.
- Right metric strip: confidence, evidence ledger count, fact count, relation count, and a derived gap closure indicator if enough data exists. If no reliable gap formula is available, show collection gap count from the graph summary or `-`.

### Main Cockpit Grid

Use a responsive grid: `lg` and wider should render 3 columns roughly `3 / 6 / 3`; narrower viewports stack sections in the same order.

Left column:

- Evidence Ledger panel with colored left borders for confirmed, conflict, warning, and unknown records.
- Fact Pool panel below or merged nearby depending on available height.
- Empty states remain visible and compact.

Center column:

- RelationshipGraphPanel remains the main interaction surface.
- Update its wrapper and graph canvas styling to match `HCS K-GRAPH / 双轴协同验证拓扑`.
- Preserve pan, zoom, selected node details, source chains, and overflow details.
- Use more reference-aligned colors for zones, edges, and nodes while retaining current graph semantics.

Right column:

- HypothesisPanel becomes the ACH matrix zone.
- QueuePanel and Agent status become an active agent pipeline zone for the selected task.
- RiskReviewPanel remains near the hypothesis area because it supports validation and contradiction reading.
- Keep existing actions and run buttons available.

### Lower Assessment Zone

Below the cockpit grid, use a two-column layout on desktop:

- Wider column: report card styled as "情报评估与对冲反制白皮书"; render `selected.report_markdown` or the existing empty report copy.
- Narrower column: PIR intelligence gaps and structured audit/memory summaries. Use existing `ReportAuditPanel` and `IntelligenceMemoryPanel` data, but present them as compact panels rather than a long mixed column.

### Overflow Lists

Entities, evidence, and relationships remain available, but move below the assessment zone or into compact expandable panels. The main cockpit should prioritize decision-making evidence, graph, hypotheses, jobs, and report.

## Component Strategy

- Add or adapt cockpit-specific CSS classes in `src/styles.css`: background grid, cockpit header, BLUF block, cockpit metrics, cockpit grid, evidence cards, ACH zone, pipeline rows, and lower assessment layout.
- Keep React changes concentrated in `src/main.tsx` unless a repeated structure deserves a small component.
- Prefer reusing existing components: `RelationshipGraphPanel`, `EvidenceLedgerPanel`, `FactPoolPanel`, `HypothesisPanel`, `QueuePanel`, `RiskReviewPanel`, `IntelligenceMemoryPanel`, `ReportAuditPanel`, `MiniMetrics`, and `DataRow`.
- Update shared panel styles rather than one-off inline styles where repeated.
- Use existing `lucide-react` icons where action buttons or status controls need icons.

## Data Flow

- No new API calls.
- Existing `selected` investigation payload remains the source for graph, facts, ledger, hypotheses, risk report, memory, markdown report, jobs, entities, evidence, and relationships.
- The cockpit header derives metrics from existing selected fields.
- Agent pipeline in the selected cockpit can use current global `agents` plus selected job state. It should not imply real per-agent assignment unless data already supports it.

## States

The redesign must preserve these states:

- No selected task: current empty state remains clear.
- Loading detail: current loading bar or equivalent visible progress remains.
- Summary missing: BLUF block uses waiting copy.
- Graph missing: graph empty state remains.
- Evidence/facts/hypotheses missing: compact empty panels remain.
- Queue running: run button and running state remain clear.
- API offline: top-level API status pill remains unchanged.

## Responsiveness

- Desktop: sidebar plus workspace, cockpit header, 3-column cockpit grid, lower 8/4 assessment grid.
- Tablet: cockpit grid becomes 1 or 2 columns depending available width, with graph before right-side validation panels if necessary.
- Mobile: all cockpit sections stack, tables remain horizontally scrollable, buttons wrap without text overflow.

## Accessibility

- Preserve keyboard focus states.
- Status colors must keep text labels.
- Graph controls keep accessible button titles.
- Contrast must remain readable on light backgrounds.
- Avoid using emoji as the only semantic marker in production UI.

## Testing And Verification

- Run `npm run build`.
- If available, run `npm run check:ui-copy`.
- Start or reuse the Vite dev server and inspect the selected dashboard at desktop and mobile widths with the in-app browser.
- Verify: no blank graph canvas, no overlapping text, controls remain clickable, empty state reads correctly, and current task actions still work.

## Acceptance Criteria

- The selected investigation detail area visually reads as the HCS dual-core control cockpit while the broader task-center workflow remains intact.
- Reference-inspired BLUF, evidence ledger, graph, ACH, pipeline, report, and gap zones are all represented.
- Existing data and actions still render without backend changes.
- The UI remains light, dense, responsive, and aligned with the existing `DESIGN.md`.
