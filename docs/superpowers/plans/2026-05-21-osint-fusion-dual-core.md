# OSINT Fusion Dual-Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 1 of the OSINT Fusion upgrade so Amass, SpiderFoot, and Sherlock findings become traceable dual-core evidence-chain candidates without requiring live tool containers.

**Architecture:** Add a focused backend fusion module that derives `OsintSignal` records from parsed tool output and investigation detail. Attach those signal hints to graph node/edge metadata and expose a compact frontend mosaic evidence chain using existing React/Vite components and CSS. Keep storage, queue contracts, and existing tool adapters intact.

**Tech Stack:** Python 3 unittest backend, existing `app.tools` adapters, existing `MemoryStore`/`SQLiteStore`, React + TypeScript + Vite frontend, existing CSS design system.

---

## File Structure

- Create `backend/app/core/osint_fusion.py`: derives OSINT signals, assigns `core_axis`, `slot_hint`, `review_status`, and provides metadata lookup helpers.
- Create `backend/tests/test_osint_fusion.py`: direct unit tests for Amass, SpiderFoot, Sherlock, same-domain email confirmation, and generic candidate behavior.
- Modify `backend/app/core/graph.py`: annotate graph nodes and edges with OSINT Fusion metadata and add `osint_signal_nodes` to graph summary.
- Modify `backend/tests/test_graph.py`: verify graph metadata carries OSINT Fusion hints for left core and right core candidates.
- Modify `backend/tests/test_tool_adapters.py`: add explicit SpiderFoot fixture coverage for company, name, username, URL, email, subdomain, and IP event types.
- Modify `frontend/src/types.ts`: add `osint_signal_nodes` to graph summary typing.
- Modify `frontend/src/graph.ts`: prioritize OSINT slot hints in fixed graph slots and visual grouping.
- Modify `frontend/scripts/test-graph-helpers.ts`: verify OSINT slot-hint placement and candidate behavior.
- Create `frontend/src/components/MosaicEvidenceChain.tsx`: compact bridge panel for tool, finding, confidence, review status, and evidence chain.
- Modify `frontend/src/main.tsx`: mount the mosaic panel in the HCS cockpit near the graph/queue.
- Modify `frontend/src/styles.css`: add restrained, dense styles for mosaic chain rows and OSINT status chips.
- Optionally modify `docs/INTEL_GATEWAY.md` and `docs/GRAPH_TEMPLATE.md` only if implementation names differ from current docs.

The current `/path/to/osint-agent-network` directory is not a git repository in this environment. If this plan is executed inside a real git worktree later, use the commit steps. If not, skip commit steps and keep verification output in the final report.

---

### Task 1: Backend OSINT Fusion Core

**Files:**
- Create: `backend/app/core/osint_fusion.py`
- Create: `backend/tests/test_osint_fusion.py`

- [ ] **Step 1: Write failing tests for derived OSINT signals**

Create `backend/tests/test_osint_fusion.py` with:

```python
import unittest

from app.core.osint_fusion import derive_osint_signals
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
)


class OsintFusionTests(unittest.TestCase):
    def test_amass_subdomain_and_ip_map_to_organization_asset_candidates(self):
        parsed = ParsedToolOutput(
            tool="amass",
            target_type="domain",
            target_value="example.com",
            entities=[
                NormalizedEntity("domain", "example.com", "amass", 0.5),
                NormalizedEntity("subdomain", "vpn.example.com", "amass", 0.5),
                NormalizedEntity("ip", "203.0.113.10", "amass", 0.45),
            ],
            evidence=[
                NormalizedEvidence("vpn.example.com", "amass_name_discovery", "amass", "Amass discovered vpn.example.com via crtsh"),
                NormalizedEvidence("203.0.113.10", "dns_resolution", "amass", "Amass linked vpn.example.com to 203.0.113.10"),
            ],
            relationships=[
                NormalizedRelationship("example.com", "vpn.example.com", "domain_has_subdomain", 0.5),
                NormalizedRelationship("vpn.example.com", "203.0.113.10", "subdomain_resolves_to_ip", 0.45),
            ],
        )

        signals = derive_osint_signals(parsed)
        by_value = {signal.entity_value: signal for signal in signals}

        self.assertEqual(by_value["vpn.example.com"].core_axis, "organization_asset")
        self.assertEqual(by_value["vpn.example.com"].slot_hint, "digital-footprint")
        self.assertEqual(by_value["vpn.example.com"].review_status, "candidate")
        self.assertEqual(by_value["203.0.113.10"].core_axis, "organization_asset")
        self.assertEqual(by_value["203.0.113.10"].slot_hint, "digital-footprint")

    def test_spiderfoot_email_same_domain_becomes_bridge_company_contact_candidate(self):
        parsed = ParsedToolOutput(
            tool="spiderfoot",
            target_type="domain",
            target_value="example.com",
            entities=[
                NormalizedEntity("domain", "example.com", "spiderfoot", 0.3),
                NormalizedEntity("email", "sales@example.com", "spiderfoot", 0.3),
                NormalizedEntity("company", "Example Trading LLC", "spiderfoot", 0.3),
                NormalizedEntity("username", "buyer-admin", "spiderfoot", 0.3),
            ],
            evidence=[
                NormalizedEvidence("sales@example.com", "spiderfoot_event", "spiderfoot", "SpiderFoot returned EMAILADDR"),
                NormalizedEvidence("Example Trading LLC", "spiderfoot_event", "spiderfoot", "SpiderFoot returned COMPANY_NAME"),
                NormalizedEvidence("buyer-admin", "spiderfoot_event", "spiderfoot", "SpiderFoot returned USERNAME"),
            ],
            relationships=[
                NormalizedRelationship("example.com", "sales@example.com", "target_has_finding", 0.3),
                NormalizedRelationship("example.com", "Example Trading LLC", "target_has_finding", 0.3),
                NormalizedRelationship("example.com", "buyer-admin", "target_has_finding", 0.3),
            ],
        )

        signals = derive_osint_signals(parsed)
        by_value = {signal.entity_value: signal for signal in signals}

        self.assertEqual(by_value["sales@example.com"].core_axis, "bridge")
        self.assertEqual(by_value["sales@example.com"].slot_hint, "company_contact")
        self.assertEqual(by_value["Example Trading LLC"].core_axis, "organization_asset")
        self.assertEqual(by_value["Example Trading LLC"].slot_hint, "landed-entity")
        self.assertEqual(by_value["buyer-admin"].core_axis, "decision_will")
        self.assertEqual(by_value["buyer-admin"].review_status, "candidate")

    def test_sherlock_profile_remains_decision_candidate(self):
        parsed = ParsedToolOutput(
            tool="sherlock",
            target_type="username",
            target_value="admin",
            entities=[
                NormalizedEntity("username", "admin", "sherlock", 0.35),
                NormalizedEntity("profile_url", "https://github.com/admin", "sherlock", 0.35),
            ],
            evidence=[
                NormalizedEvidence("https://github.com/admin", "profile_exists", "sherlock", "Sherlock claimed profile on GitHub"),
            ],
            relationships=[
                NormalizedRelationship("admin", "https://github.com/admin", "username_has_profile", 0.35),
            ],
        )

        signals = derive_osint_signals(parsed)
        by_value = {signal.entity_value: signal for signal in signals}

        self.assertEqual(by_value["admin"].core_axis, "decision_will")
        self.assertEqual(by_value["admin"].slot_hint, "persona-role")
        self.assertEqual(by_value["https://github.com/admin"].core_axis, "decision_will")
        self.assertEqual(by_value["https://github.com/admin"].slot_hint, "persona-role")
        self.assertEqual(by_value["https://github.com/admin"].review_status, "candidate")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_osint_fusion
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.osint_fusion'`.

- [ ] **Step 3: Implement `osint_fusion.py`**

Create `backend/app/core/osint_fusion.py` with:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
from urllib.parse import urlsplit

from app.tools.base import ParsedToolOutput


ORGANIZATION_AXIS = "organization_asset"
DECISION_AXIS = "decision_will"
BRIDGE_AXIS = "bridge"


@dataclass(frozen=True)
class OsintSignal:
    signal_id: str
    tool: str
    target_type: str
    target_value: str
    entity_type: str
    entity_value: str
    evidence_kind: str
    relationship_type: str
    confidence: float
    core_axis: str
    slot_hint: str
    review_status: str
    source_tier: str

    def to_dict(self) -> dict:
        return asdict(self)


def derive_osint_signals(parsed: ParsedToolOutput) -> list[OsintSignal]:
    signals: list[OsintSignal] = []
    evidence_by_value = {item.entity_value: item for item in parsed.evidence}
    relationship_by_to = {item.to_value: item for item in parsed.relationships}
    for entity in parsed.entities:
        classification = classify_osint_entity(
            tool=parsed.tool,
            target_type=parsed.target_type,
            target_value=parsed.target_value,
            entity_type=entity.type,
            entity_value=entity.value,
        )
        if classification is None:
            continue
        evidence = evidence_by_value.get(entity.value)
        relationship = relationship_by_to.get(entity.value)
        core_axis, slot_hint, review_status = classification
        signals.append(
            OsintSignal(
                signal_id=_signal_id(parsed.tool, entity.type, entity.value),
                tool=parsed.tool,
                target_type=parsed.target_type,
                target_value=parsed.target_value,
                entity_type=entity.type,
                entity_value=entity.value,
                evidence_kind=evidence.evidence_kind if evidence else "",
                relationship_type=relationship.relationship_type if relationship else "",
                confidence=entity.confidence,
                core_axis=core_axis,
                slot_hint=slot_hint,
                review_status=review_status,
                source_tier="passive_osint",
            )
        )
    return signals


def derive_osint_signals_from_detail(detail: dict) -> list[OsintSignal]:
    relationships_by_to = {
        str(item.get("to_value") or ""): str(item.get("relationship_type") or "")
        for item in detail.get("relationships", [])
    }
    evidence_by_value = {
        str(item.get("entity_value") or ""): str(item.get("evidence_kind") or "")
        for item in detail.get("evidence", [])
    }
    signals: list[OsintSignal] = []
    for entity in detail.get("entities", []):
        tool = str(entity.get("source_tool") or "")
        entity_type = str(entity.get("type") or "")
        entity_value = str(entity.get("value") or "")
        classification = classify_osint_entity(
            tool=tool,
            target_type=str(detail.get("seed_type") or ""),
            target_value=str(detail.get("seed_value") or ""),
            entity_type=entity_type,
            entity_value=entity_value,
        )
        if classification is None:
            continue
        core_axis, slot_hint, review_status = classification
        signals.append(
            OsintSignal(
                signal_id=_signal_id(tool, entity_type, entity_value),
                tool=tool,
                target_type=str(detail.get("seed_type") or ""),
                target_value=str(detail.get("seed_value") or ""),
                entity_type=entity_type,
                entity_value=entity_value,
                evidence_kind=evidence_by_value.get(entity_value, ""),
                relationship_type=relationships_by_to.get(entity_value, ""),
                confidence=float(entity.get("confidence") or 0.0),
                core_axis=core_axis,
                slot_hint=slot_hint,
                review_status=review_status,
                source_tier="passive_osint",
            )
        )
    return signals


def signal_metadata_by_value(detail: dict) -> dict[str, dict]:
    return {signal.entity_value: signal.to_dict() for signal in derive_osint_signals_from_detail(detail)}


def classify_osint_entity(
    tool: str,
    target_type: str,
    target_value: str,
    entity_type: str,
    entity_value: str,
) -> tuple[str, str, str] | None:
    tool = tool.lower()
    if tool not in {"amass", "spiderfoot", "sherlock"}:
        return None

    if tool == "amass":
        if entity_type in {"subdomain", "ip"}:
            return ORGANIZATION_AXIS, "digital-footprint", "candidate"
        if entity_type == "domain":
            return ORGANIZATION_AXIS, "company_website", "candidate"
        return None

    if tool == "spiderfoot":
        if entity_type == "email":
            slot = "company_contact" if _same_email_domain(entity_value, target_value) else "contact-channel"
            return BRIDGE_AXIS, slot, "candidate"
        if entity_type in {"url", "subdomain", "ip", "domain"}:
            return ORGANIZATION_AXIS, "digital-footprint", "candidate"
        if entity_type == "company":
            return ORGANIZATION_AXIS, "landed-entity", "candidate"
        if entity_type in {"real_name", "username"}:
            return DECISION_AXIS, "persona-role", "candidate"
        return None

    if tool == "sherlock":
        if entity_type in {"username", "profile_url", "social_profile", "platform_account"}:
            return DECISION_AXIS, "persona-role", "candidate"
        return None

    return None


def _same_email_domain(email: str, target_value: str) -> bool:
    if "@" not in email:
        return False
    email_domain = email.rsplit("@", 1)[1].lower()
    target_domain = _domain_like(target_value)
    return bool(target_domain and email_domain == target_domain)


def _domain_like(value: str) -> str:
    value = value.strip().lower()
    if "@" in value:
        return value.rsplit("@", 1)[1]
    if value.startswith(("http://", "https://")):
        return (urlsplit(value).hostname or "").removeprefix("www.")
    return value.removeprefix("www.")


def _signal_id(tool: str, entity_type: str, entity_value: str) -> str:
    digest = sha1(f"{tool}:{entity_type}:{entity_value}".encode("utf-8")).hexdigest()[:16]
    return f"osint:{digest}"
```

- [ ] **Step 4: Run backend fusion tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_osint_fusion
```

Expected: PASS.

- [ ] **Step 5: Commit if in git worktree**

```bash
git add backend/app/core/osint_fusion.py backend/tests/test_osint_fusion.py
git commit -m "feat: add osint fusion classification"
```

Expected: commit succeeds. If the directory has no `.git`, skip this step.

---

### Task 2: Tool Adapter Fixture Coverage

**Files:**
- Modify: `backend/tests/test_tool_adapters.py`

- [ ] **Step 1: Add SpiderFoot fixture test**

Append this test method to `SpiderFootAdapterTests` in `backend/tests/test_tool_adapters.py`. If the class is lower in the file, place it inside that existing class.

```python
    def test_parser_maps_core_osint_event_types_for_dual_core_fusion(self):
        adapter = SpiderFootAdapter()
        raw = {
            "results": [
                {"type": "EMAILADDR", "data": "sales@example.com", "source": "sfp_email"},
                {"type": "INTERNET_NAME", "data": "vpn.example.com", "source": "sfp_dns"},
                {"type": "IP_ADDRESS", "data": "203.0.113.10", "source": "sfp_dns"},
                {"type": "URL", "data": "https://example.com/contact", "source": "sfp_spider"},
                {"type": "USERNAME", "data": "buyer-admin", "source": "sfp_accounts"},
                {"type": "HUMAN_NAME", "data": "Alice Buyer", "source": "sfp_names"},
                {"type": "COMPANY_NAME", "data": "Example Trading LLC", "source": "sfp_company"},
            ]
        }

        parsed = adapter.parse_json(raw, target_type="domain", target_value="example.com")

        entities = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("email", "sales@example.com"), entities)
        self.assertIn(("subdomain", "vpn.example.com"), entities)
        self.assertIn(("ip", "203.0.113.10"), entities)
        self.assertIn(("url", "https://example.com/contact"), entities)
        self.assertIn(("username", "buyer-admin"), entities)
        self.assertIn(("real_name", "Alice Buyer"), entities)
        self.assertIn(("company", "Example Trading LLC"), entities)
        self.assertIn(("sales@example.com", "spiderfoot_event"), evidence)
        self.assertIn(("example.com", "buyer-admin", "target_has_finding"), relationships)
```

- [ ] **Step 2: Run the specific adapter test**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_tool_adapters.SpiderFootAdapterTests.test_parser_maps_core_osint_event_types_for_dual_core_fusion
```

Expected: PASS. If it fails because the SpiderFoot class is not named `SpiderFootAdapterTests`, run `rg -n "class SpiderFoot" backend/tests/test_tool_adapters.py`, place the method in the discovered class, then rerun.

- [ ] **Step 3: Run all adapter tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_tool_adapters
```

Expected: PASS.

- [ ] **Step 4: Commit if in git worktree**

```bash
git add backend/tests/test_tool_adapters.py
git commit -m "test: cover spiderfoot osint event mapping"
```

Expected: commit succeeds. If the directory has no `.git`, skip this step.

---

### Task 3: Graph Metadata Integration

**Files:**
- Modify: `backend/app/core/graph.py`
- Modify: `backend/tests/test_graph.py`

- [ ] **Step 1: Add failing graph metadata test**

Add this test method to `InvestigationGraphTests` in `backend/tests/test_graph.py`:

```python
    def test_graph_nodes_include_osint_fusion_metadata(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Example dual-core OSINT",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )
        store.add_entity(investigation.id, "subdomain", "vpn.example.com", "amass", 0.5)
        store.add_entity(investigation.id, "ip", "203.0.113.10", "amass", 0.45)
        store.add_entity(investigation.id, "profile_url", "https://github.com/admin", "sherlock", 0.35)
        store.add_evidence(
            investigation.id,
            "vpn.example.com",
            "amass_name_discovery",
            "amass",
            "Amass discovered vpn.example.com via crtsh",
        )
        store.add_evidence(
            investigation.id,
            "https://github.com/admin",
            "profile_exists",
            "sherlock",
            "Sherlock claimed profile on GitHub",
        )
        store.add_relationship(
            investigation.id,
            "example.com",
            "vpn.example.com",
            "domain_has_subdomain",
            0.5,
        )
        store.add_relationship(
            investigation.id,
            "admin",
            "https://github.com/admin",
            "username_has_profile",
            0.35,
        )

        graph = store.get_investigation(investigation.id)["graph"]
        by_value = {node["value"]: node for node in graph["nodes"]}

        self.assertEqual(by_value["vpn.example.com"]["metadata"]["core_axis"], "organization_asset")
        self.assertEqual(by_value["vpn.example.com"]["metadata"]["slot_hint"], "digital-footprint")
        self.assertEqual(by_value["vpn.example.com"]["metadata"]["review_status"], "candidate")
        self.assertEqual(by_value["https://github.com/admin"]["metadata"]["core_axis"], "decision_will")
        self.assertEqual(by_value["https://github.com/admin"]["metadata"]["slot_hint"], "persona-role")
        self.assertGreaterEqual(graph["summary"]["osint_signal_nodes"], 3)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_graph.InvestigationGraphTests.test_graph_nodes_include_osint_fusion_metadata
```

Expected: FAIL with missing `core_axis` or `osint_signal_nodes`.

- [ ] **Step 3: Annotate graph nodes and summary**

In `backend/app/core/graph.py`, add the import near the top:

```python
from app.core.osint_fusion import signal_metadata_by_value
```

Inside `build_investigation_graph`, after `value_to_node: dict[str, str] = {}`, add:

```python
    osint_metadata = signal_metadata_by_value(detail)
```

In the entity `add_node` call, replace:

```python
                "metadata": {"entity_type": entity.get("type", "entity")},
```

with:

```python
                "metadata": {
                    "entity_type": entity.get("type", "entity"),
                    **osint_metadata.get(entity_value, {}),
                },
```

In the evidence node metadata block, add OSINT metadata for `entity_value`:

```python
                    **osint_metadata.get(entity_value, {}),
```

The evidence metadata block should become:

```python
                "metadata": {
                    "evidence_kind": evidence.get("evidence_kind", "evidence"),
                    "snippet": evidence.get("snippet", ""),
                    **osint_metadata.get(entity_value, {}),
                },
```

In the returned summary dict, add:

```python
            "osint_signal_nodes": sum(
                1 for node in nodes if node.get("metadata", {}).get("core_axis")
            ),
```

- [ ] **Step 4: Run graph tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_graph
```

Expected: PASS.

- [ ] **Step 5: Commit if in git worktree**

```bash
git add backend/app/core/graph.py backend/tests/test_graph.py
git commit -m "feat: attach osint fusion metadata to graph"
```

Expected: commit succeeds. If the directory has no `.git`, skip this step.

---

### Task 4: Frontend Graph Slot Priority

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/graph.ts`
- Modify: `frontend/scripts/test-graph-helpers.ts`

- [ ] **Step 1: Add failing frontend graph helper assertions**

Append this block near the end of `frontend/scripts/test-graph-helpers.ts`:

```ts
const osintNodes: GraphNode[] = [
  {
    id: "entity:subdomain",
    label: "vpn.example.com",
    type: "entity",
    value: "vpn.example.com",
    source_tool: "amass",
    confidence: 0.5,
    risk_level: "",
    evidence_count: 1,
    metadata: {
      entity_type: "subdomain",
      core_axis: "organization_asset",
      slot_hint: "digital-footprint",
      review_status: "candidate",
    },
  },
  {
    id: "entity:profile",
    label: "https://github.com/admin",
    type: "entity",
    value: "https://github.com/admin",
    source_tool: "sherlock",
    confidence: 0.35,
    risk_level: "",
    evidence_count: 1,
    metadata: {
      entity_type: "profile_url",
      core_axis: "decision_will",
      slot_hint: "persona-role",
      review_status: "candidate",
    },
  },
];

const osintDisplayNodes = graphDisplayNodes(osintNodes);
const subdomainSlot = osintDisplayNodes.find((node) => node.value === "vpn.example.com")?.metadata.template_slot;
const profileSlot = osintDisplayNodes.find((node) => node.value === "https://github.com/admin")?.metadata.template_slot;

assert.equal(subdomainSlot, "company_website", "OSINT digital-footprint domains should occupy the organization-side digital asset slot");
assert.equal(profileSlot, "social_profile", "Sherlock public-profile candidates should occupy the decision-side social profile slot");
assert.equal(nodeVisualGroup(osintNodes[0]), "contact", "subdomain findings should render as contact/digital assets");
```

- [ ] **Step 2: Run script to verify failure**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-graph-helpers.ts
```

Expected: FAIL because `subdomain` is not currently matched to the company website slot or because OSINT hint priority is not recognized.

- [ ] **Step 3: Update graph types**

In `frontend/src/types.ts`, add `osint_signal_nodes?: number;` to `InvestigationGraph.summary`:

```ts
    osint_signal_nodes?: number;
```

- [ ] **Step 4: Update graph slot matching and priority**

In `frontend/src/graph.ts`, change the `company_website` matcher from:

```ts
    mainSlot("company_website", "企业网址", 1010, 515, (node) => ["domain", "profile_url", "external_link"].includes(entityTypeOf(node))),
```

to:

```ts
    mainSlot("company_website", "企业网址", 1010, 515, (node) =>
      ["domain", "subdomain", "url", "profile_url", "external_link", "ip"].includes(entityTypeOf(node))
      && metadataString(node, "core_axis") !== "decision_will",
    ),
```

Add this helper below `entityTypeOf`:

```ts
function metadataString(node: GraphNode, key: string) {
  const value = node.metadata[key];
  return typeof value === "string" ? value : "";
}
```

In `slotNodePriority`, after `const text = nodeSearchText(node);`, add:

```ts
  const slotHint = metadataString(node, "slot_hint");
  if (slotHint && slotHint === slotId) {
    score += 5;
  }
  if (slotId === "company_website" && slotHint === "digital-footprint") {
    score += 4;
  }
  if (slotId === "social_profile" && slotHint === "persona-role") {
    score += 4;
  }
```

- [ ] **Step 5: Run frontend helper test**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-graph-helpers.ts
```

Expected: PASS.

- [ ] **Step 6: Commit if in git worktree**

```bash
git add frontend/src/types.ts frontend/src/graph.ts frontend/scripts/test-graph-helpers.ts
git commit -m "feat: prioritize osint hints in graph slots"
```

Expected: commit succeeds. If the directory has no `.git`, skip this step.

---

### Task 5: Mosaic Evidence Chain Panel

**Files:**
- Create: `frontend/src/components/MosaicEvidenceChain.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Create the panel component**

Create `frontend/src/components/MosaicEvidenceChain.tsx`:

```tsx
import type { Entity, EvidenceItem, Relationship } from "../types";

type MosaicEvidenceChainProps = {
  entities?: Entity[];
  evidence?: EvidenceItem[];
  relationships?: Relationship[];
};

const osintTools = new Set(["amass", "spiderfoot", "sherlock"]);

function statusFor(entity: Entity) {
  if (entity.confidence >= 0.7) {
    return "confirmed";
  }
  return "candidate";
}

function slotFor(entity: Entity) {
  if (entity.source_tool === "amass") {
    return "组织资产核 / 数字外延";
  }
  if (entity.source_tool === "sherlock") {
    return "意志决策核 / 公开主页候选";
  }
  if (entity.type === "email") {
    return "桥接链 / 联系方式";
  }
  if (["company", "domain", "subdomain", "ip", "url"].includes(entity.type)) {
    return "组织资产核 / 被动富集";
  }
  return "意志决策核 / 候选画像";
}

function evidenceFor(entity: Entity, evidence: EvidenceItem[]) {
  return evidence.find((item) => item.entity_value === entity.value);
}

function triggerFor(entity: Entity, relationships: Relationship[]) {
  const relationship = relationships.find((item) => item.to_value === entity.value);
  if (!relationship) {
    return "seed -> finding";
  }
  return `${relationship.from_value} -> ${relationship.relationship_type}`;
}

export function MosaicEvidenceChain({ entities = [], evidence = [], relationships = [] }: MosaicEvidenceChainProps) {
  const rows = entities
    .filter((entity) => osintTools.has(entity.source_tool))
    .slice()
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 8)
    .map((entity) => ({
      entity,
      evidence: evidenceFor(entity, evidence),
      trigger: triggerFor(entity, relationships),
      status: statusFor(entity),
      slot: slotFor(entity),
    }));

  return (
    <article className="mosaic-chain-panel">
      <div className="section-heading">
        <h3>马赛克证据链</h3>
        <span>{rows.length} 条</span>
      </div>
      <div className="mosaic-chain-list">
        {rows.map((row) => (
          <div key={`${row.entity.source_tool}:${row.entity.type}:${row.entity.value}`} className={`mosaic-chain-row is-${row.status}`}>
            <div className="mosaic-chain-head">
              <strong>{row.entity.source_tool}</strong>
              <span>{row.slot}</span>
              <em>{row.status === "confirmed" ? "已确认" : "候选待核"}</em>
            </div>
            <p>{row.entity.type}: {row.entity.value}</p>
            <small>{row.trigger}</small>
            <small>{row.evidence?.snippet ?? row.evidence?.evidence_kind ?? "暂无证据片段，等待工具回写补齐。"}</small>
          </div>
        ))}
        {!rows.length ? <div className="empty compact">暂无 Amass / SpiderFoot / Sherlock 证据链。</div> : null}
      </div>
    </article>
  );
}
```

- [ ] **Step 2: Mount the panel in main cockpit**

In `frontend/src/main.tsx`, add the import near the other component imports:

```tsx
import { MosaicEvidenceChain } from "./components/MosaicEvidenceChain";
```

After the `HcsTemplateGraph` component in the `hcs-graph-core` section, add:

```tsx
                <MosaicEvidenceChain
                  entities={selected.entities}
                  evidence={selected.evidence}
                  relationships={selected.relationships}
                />
```

- [ ] **Step 3: Add CSS**

Append to `frontend/src/styles.css`:

```css
.mosaic-chain-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  padding: 12px;
}

.mosaic-chain-list {
  display: grid;
  gap: 8px;
}

.mosaic-chain-row {
  border: 1px solid var(--border);
  border-left: 3px solid #94a3b8;
  border-radius: 8px;
  background: #f8fafc;
  padding: 9px 10px;
}

.mosaic-chain-row.is-confirmed {
  border-left-color: #10b981;
}

.mosaic-chain-row.is-candidate {
  border-left-color: #06b6d4;
}

.mosaic-chain-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.mosaic-chain-head strong {
  font-family: var(--mono-font);
  color: #0f172a;
}

.mosaic-chain-head span {
  color: #475569;
}

.mosaic-chain-head em {
  margin-left: auto;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  padding: 2px 7px;
  color: #334155;
  font-style: normal;
  font-size: 11px;
  white-space: nowrap;
}

.mosaic-chain-row p {
  margin: 6px 0 4px;
  color: #0f172a;
  font-family: var(--mono-font);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.mosaic-chain-row small {
  display: block;
  color: #64748b;
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit if in git worktree**

```bash
git add frontend/src/components/MosaicEvidenceChain.tsx frontend/src/main.tsx frontend/src/styles.css
git commit -m "feat: show mosaic osint evidence chain"
```

Expected: commit succeeds. If the directory has no `.git`, skip this step.

---

### Task 6: Queue Status Clarity

**Files:**
- Modify: `frontend/src/components/QueuePanel.tsx`

- [ ] **Step 1: Add explicit OSINT queue helper display**

In `frontend/src/components/QueuePanel.tsx`, add this helper above `export function QueuePanel`:

```tsx
function queueHint(job: Job) {
  if (job.tool_name === "spiderfoot" && job.status === "BLOCKED") {
    return "SpiderFoot 需要 SPIDERFOOT_BASE_URL；当前任务保持可追溯阻塞状态。";
  }
  if (job.status === "BLOCKED") {
    return "工具缺命令或缺配置，等待环境补齐后重跑。";
  }
  if (["amass", "spiderfoot", "sherlock"].includes(job.tool_name) && job.status === "COMPLETED") {
    return "工具已回写，结果默认作为候选证据进入交叉验证。";
  }
  if (["amass", "spiderfoot", "sherlock"].includes(job.tool_name) && job.status === "PARTIAL_FAILED") {
    return "工具部分失败，保留已有 artifact 与事件摘要供复核。";
  }
  return "";
}
```

Replace both `body={...}` expressions in `DataRow` calls with:

```tsx
            body={[
              job.output_contract ? `产出：${job.output_contract}${job.depends_on ? `；依赖：${job.depends_on}` : ""}` : "",
              queueHint(job),
            ].filter(Boolean).join("；")}
```

Apply the same replacement in the expanded job list.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 3: Commit if in git worktree**

```bash
git add frontend/src/components/QueuePanel.tsx
git commit -m "feat: clarify osint queue states"
```

Expected: commit succeeds. If the directory has no `.git`, skip this step.

---

### Task 7: Verification And Documentation Check

**Files:**
- Modify only if needed after implementation: `docs/INTEL_GATEWAY.md`, `docs/GRAPH_TEMPLATE.md`

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest \
  backend.tests.test_osint_fusion \
  backend.tests.test_tool_adapters \
  backend.tests.test_graph
```

Expected: PASS.

- [ ] **Step 2: Run full verification script**

Run:

```bash
bash scripts/verify.sh
```

Expected: PASS. If it fails in frontend dependency or environment setup, capture the exact failing command and rerun the narrow command after fixing the implementation.

- [ ] **Step 3: Run a terminology consistency check**

Run:

```bash
rg -n "osint_signal_nodes|core_axis|slot_hint|review_status|MosaicEvidenceChain|马赛克证据链" backend frontend docs
```

Expected: Results include the new backend module/tests, graph metadata, frontend panel, and design/plan docs. No unexpected spelling variants such as `reviewState`, `slotHint`, or `osintSignals` should appear unless deliberately localized inside React component variables.

- [ ] **Step 4: Commit docs if changed and in git worktree**

```bash
git add docs/INTEL_GATEWAY.md docs/GRAPH_TEMPLATE.md
git commit -m "docs: document osint fusion graph semantics"
```

Expected: commit succeeds if docs changed. If docs did not change or the directory has no `.git`, skip this step.

---

## Self-Review

- Spec coverage: Tasks cover Phase 1 fusion classification, adapter fixture coverage, graph metadata, frontend graph slot mapping, mosaic evidence chain display, queue status clarity, and verification. Phase 2 remains documented in the design but intentionally not implemented in this Phase 1 plan.
- Placeholder scan: No `TBD`, `TODO`, or "similar to" placeholders remain. Each code change step includes concrete code.
- Type consistency: Backend uses `core_axis`, `slot_hint`, `review_status`, and `osint_signal_nodes`. Frontend reads those exact metadata keys and summary field.

