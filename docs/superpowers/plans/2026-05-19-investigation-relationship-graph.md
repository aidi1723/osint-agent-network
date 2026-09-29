# Investigation Relationship Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a derived investigation graph and render it in the existing analyst data board.

**Architecture:** Backend derives a stable `graph` object from existing investigation detail data, so clients do not duplicate relationship logic. Frontend renders the graph with a dependency-free SVG component that follows the existing dense console design.

**Tech Stack:** Python unittest backend, in-memory and SQLite stores, React 19, TypeScript, Vite, lucide-react, CSS.

---

### Task 1: Backend Graph Derivation

**Files:**
- Create: `backend/app/core/graph.py`
- Modify: `backend/app/services/store.py`
- Test: `backend/tests/test_graph.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_graph.py` with tests that call `MemoryStore` and `SQLiteStore`, add username/profile/location/bio entities, evidence, relationships, and a risk report, then assert `detail["graph"]` includes seed, entity, evidence, and risk nodes plus relationship/evidence/risk edges.

- [ ] **Step 2: Run the tests and confirm failure**

Run: `python3 -m unittest backend.tests.test_graph -v`

Expected: failure because `graph` is missing.

- [ ] **Step 3: Implement graph derivation**

Create `backend/app/core/graph.py` with `build_investigation_graph(detail: dict) -> dict`. Deduplicate nodes by stable ids, resolve relationship endpoints by entity value, link evidence to entities, link risk signals to evidence values or seed, and return `nodes`, `edges`, and `summary`.

- [ ] **Step 4: Attach graph to stores**

Import `build_investigation_graph` in `backend/app/services/store.py` and set `data["graph"] = build_investigation_graph(data)` in both memory and SQLite investigation detail paths after `risk_report` is available.

- [ ] **Step 5: Run backend graph tests**

Run: `python3 -m unittest backend.tests.test_graph -v`

Expected: all graph tests pass.

### Task 2: Frontend Graph Panel

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add TypeScript graph types**

Add `InvestigationGraph`, `GraphNode`, and `GraphEdge` types to match the backend payload and add `graph?: InvestigationGraph` to `Investigation`.

- [ ] **Step 2: Add `RelationshipGraphPanel`**

Implement a dependency-free SVG panel that accepts `selected.graph`, computes lane-based node positions, renders edges, edge labels, nodes, legend, summary chips, and selected-node details.

- [ ] **Step 3: Insert the panel**

Place `RelationshipGraphPanel graph={selected.graph}` between `RiskReviewPanel` and the mini metrics in the left board column.

- [ ] **Step 4: Style the panel**

Add compact graph CSS using existing token values: white/pale gray surfaces, cool borders, blue/cyan accents, amber/red risk states, 8px radius, readable labels, and responsive single-column behavior.

- [ ] **Step 5: Run frontend build**

Run: `npm run build`

Expected: TypeScript and Vite build succeed.

### Task 3: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run backend test suite**

Run: `python3 -m unittest discover -s backend/tests -v`

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend build**

Run: `npm run build`

Expected: build succeeds.

- [ ] **Step 3: UI consistency check**

Review the graph panel against `DESIGN.md` and `ui-audit-checklist.md`: density, typography, surfaces, hover/focus states, responsive behavior, and accessibility labels.
