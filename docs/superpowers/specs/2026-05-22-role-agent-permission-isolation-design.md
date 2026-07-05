# Role Agent Permission Isolation Design

Version: 1.0
Updated: 2026-05-22
Status: Ready for implementation planning

## 1. Purpose

This phase adds runtime responsibility isolation for local role agents. It adapts the reader / verifier / reporter separation used by Anthropic's reference agent cookbooks to the existing 皇城司 local worker model.

The goal is to prevent collection roles from writing final facts, prevent verification roles from publishing reports, and prevent reporting roles from collecting new evidence.

## 2. Current Baseline

The local Worker executes non-`tool_agent` jobs through `run_role_agent`. That function directly receives the store and can call any store write method. In practice the current code behaves responsibly, but the boundary is convention-based rather than enforced.

This phase keeps the same local scheduling and job flow. It adds a permission-aware writer wrapper around the store for local role-agent code.

## 3. Scope

### In Scope

- Add a role tier map for local role agents.
- Add a `PermissionedRoleStore` wrapper.
- Route `run_role_agent` internals through the wrapper.
- Add tests proving forbidden writes raise `PermissionError`.
- Keep existing local role-agent workflows passing.

### Out of Scope

- No OS sandboxing.
- No process isolation.
- No token-level permission model for external HTTP agents.
- No MCP permission system.
- No UI changes.
- No changes to Worker scheduling.

## 4. Permission Model

Role tiers:

- `reader`: may write entities, basic evidence, evidence records, and relationships. It may not write facts, score hypotheses, or complete reports.
- `verifier`: may write facts, hypotheses, and hypothesis scores. It may not collect new entities/evidence or complete reports.
- `reporter`: may complete the task and write the report. It may not collect new entities/evidence/relationships or write facts.

Initial role mapping:

```text
enterprise_intel_agent        -> reader
social_intel_agent            -> reader
contact_discovery_agent       -> reader
supply_chain_agent            -> reader
purchase_intent_agent         -> reader
news_intel_agent              -> reader
search_planning_agent         -> reader
cross_verification_agent      -> verifier
analysis_judgement_agent      -> reporter
```

Special case: `constrained_query_planning` is a search-planning job and remains reader-tier because it writes collection evidence only.

## 5. Architecture

Add `backend/app/core/agent_permissions.py`:

```python
def tier_for_role(agent_role: str) -> str:
    ...

class PermissionedRoleStore:
    ...
```

`PermissionedRoleStore` forwards reads and allowed writes to the real store. Forbidden write attempts raise `PermissionError` with a stable message.

`run_role_agent` computes the tier from `job["agent_role"]` and passes a permissioned store into private role-agent routines. Private routines keep their current signatures as much as possible.

## 6. Allowed Operations

Reader allows:

- `get_investigation`
- `add_entity`
- `add_evidence`
- `add_evidence_record`
- `add_relationship`

Verifier allows:

- `get_investigation`
- `add_fact`
- `add_hypothesis`
- `score_hypotheses`

Reporter allows:

- `get_investigation`
- `complete_task`

All tiers may read investigation detail. Only the methods above are exposed by the wrapper.

## 7. Runtime Behavior

If role code tries to call a forbidden method, the wrapper raises `PermissionError`. The Worker already catches exceptions in `_execute_role_job`, marks the job failed, and records an event. Direct unit tests should also exercise the wrapper without going through Worker.

Existing local role-agent behavior should remain functionally unchanged:

- Collection roles still write candidate entities/evidence/relationships.
- Cross-verification still writes facts and hypotheses.
- Analysis judgement still writes the structured report and completes the task.

## 8. Testing

Add tests for:

- Reader cannot call `add_fact`.
- Verifier cannot call `complete_task`.
- Reporter cannot call `add_entity`.
- `run_role_agent` still completes collection, verification, and analysis jobs with permissioned stores.
- Full `test_role_agents` suite passes.

## 9. Success Criteria

- Forbidden writes raise `PermissionError`.
- Existing local role-agent tests pass.
- Full project verification passes.
- Documentation states this is local responsibility isolation, not OS sandboxing.
