# Agent Writeback Validation Design

Version: 1.0
Updated: 2026-05-22
Status: Ready for implementation planning

## 1. Purpose

This phase adds deterministic validation for structured Agent write-back payloads. The goal is to prevent external or local agents from writing malformed entities, evidence, relationships, evidence-ledger records, or facts into the investigation store.

This phase builds on the Agent / Skill governance layer but changes runtime behavior only at the API boundary for selected `/api/agent/*` write endpoints.

## 2. Current Baseline

The project already validates some write paths indirectly through store methods and `FactRecord` validation. However, several API endpoints read fields directly from JSON payloads and rely on `KeyError`, defaults, or downstream conversion failures.

The project also has `backend/app/core/intel_schema.json`, which defines required fields and allowed values for core intelligence objects. This phase turns the most important parts of that schema into a small Python validator used by the API.

## 3. Scope

### In Scope

Validate these endpoints before store writes:

- `/api/agent/entities`
- `/api/agent/evidence`
- `/api/agent/evidence-records`
- `/api/agent/facts`
- `/api/agent/relationships`

Validation covers:

- Required fields.
- Non-empty string fields.
- Confidence and credibility numeric bounds.
- `source_type` allowlist for evidence-ledger records.
- Fact status allowlist.
- Confirmed or likely facts requiring `admiralty_code` and `evidence_ids`.
- Relationship direction fields.

### Out of Scope

- No validation for `/api/agent/tasks/*/complete`.
- No validation for `/api/agent/hypotheses`.
- No validation for `/api/agent/hypotheses/score`.
- No database schema changes.
- No front-end changes.
- No JSON Schema dependency.

## 4. Architecture

Add `backend/app/core/agent_payload_validation.py`.

The module exposes:

```python
def validate_agent_payload(kind: str, payload: dict) -> list[str]:
    ...
```

The API calls this before store writes:

```python
errors = validate_agent_payload("entities", payload)
if errors:
    self._json({"detail": "validation failed", "errors": errors}, status=400)
    return
```

Use plain Python rules instead of adding a JSON Schema package. This keeps the project lightweight and makes validation messages stable for tests.

## 5. Validation Rules

### Entities

Payload must include:

- `task_id`
- `entities`

Each item in `entities` must include:

- `type`
- `value`
- `source_tool`
- `confidence`

`confidence` must be a number from `0.0` to `1.0`.

### Evidence

Payload must include:

- `task_id`
- `entity_value`
- `evidence_kind`
- `source_tool`
- `snippet`

Required strings must be non-empty.

### Evidence Records

Payload must include:

- `task_id`
- `source_url`
- `source_type`
- `source_tool`
- `snippet`
- `credibility`

`source_type` must be in the allowlist from `intel_schema.json`. `credibility` must be a number from `0.0` to `1.0`.

### Facts

Payload must include:

- `task_id`
- `statement`
- `subject`
- `predicate`
- `object`
- `status`
- `confidence`

`status` must be one of:

- `CONFIRMED`
- `LIKELY`
- `CONTRADICTED`
- `RETIRED`
- `NEEDS_REVIEW`

`confidence` must be a number from `0.0` to `1.0`.

When status is `CONFIRMED` or `LIKELY`, payload must also include:

- `admiralty_code`
- non-empty `evidence_ids`

### Relationships

Payload must include:

- `task_id`
- `from`
- `to`
- `relationship_type`
- `confidence`

`confidence` must be a number from `0.0` to `1.0`.

## 6. Error Response

Invalid payloads return:

```json
{
  "detail": "validation failed",
  "errors": ["field message"]
}
```

The response status is `400`.

## 7. Testing

Add focused tests to `backend/tests/test_agent_protocol.py`:

- Invalid entity payload is rejected.
- Invalid evidence payload is rejected.
- Invalid evidence record source type is rejected.
- Confirmed fact without evidence IDs is rejected.
- Invalid relationship payload is rejected.

Existing valid write-back tests must continue passing.

## 8. Success Criteria

- Invalid structured write-back payloads return deterministic `400` responses.
- Existing valid write-back tests still pass.
- `PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol` passes.
- `python3 scripts/check_agents.py` passes.
- `bash scripts/verify.sh` passes.
