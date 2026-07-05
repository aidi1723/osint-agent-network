# Agent Writeback Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate structured `/api/agent/*` write-back payloads before they mutate the investigation store.

**Architecture:** Add a lightweight validator in `backend/app/core/agent_payload_validation.py` and call it from selected API endpoints in `backend/app/main.py`. Tests exercise HTTP behavior so the validation contract is verified at the real boundary.

**Tech Stack:** Python standard library, existing `unittest` HTTP test harness, existing Python `http.server` API.

---

## File Structure

- Create `backend/app/core/agent_payload_validation.py`: validation rules and stable error messages.
- Modify `backend/app/main.py`: call `validate_agent_payload` before store writes for selected endpoints.
- Modify `backend/tests/test_agent_protocol.py`: add HTTP rejection tests.
- Modify `README.md`: mention write-back validation in the governance section.

---

### Task 1: Write HTTP Rejection Tests

**Files:**
- Modify: `backend/tests/test_agent_protocol.py`

- [ ] **Step 1: Add helper imports and tests**

Add these tests inside `AgentProtocolTests` after `test_agent_http_routes_accept_core_v2_protocol_writes`:

```python
    def test_agent_http_rejects_invalid_entity_payload(self):
        status, payload = _post_json_expect_error(
            "/api/agent/entities",
            {"task_id": "task-1", "entities": [{"type": "domain", "value": "", "source_tool": "agent", "confidence": 1.2}]},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("entities[0].value is required" in error for error in payload["errors"]))
        self.assertTrue(any("entities[0].confidence must be between 0 and 1" in error for error in payload["errors"]))

    def test_agent_http_rejects_invalid_evidence_payload(self):
        status, payload = _post_json_expect_error(
            "/api/agent/evidence",
            {"task_id": "task-1", "entity_value": "example.com", "evidence_kind": "", "source_tool": "agent", "snippet": ""},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("evidence_kind is required" in error for error in payload["errors"]))
        self.assertTrue(any("snippet is required" in error for error in payload["errors"]))

    def test_agent_http_rejects_invalid_evidence_record_source_type(self):
        status, payload = _post_json_expect_error(
            "/api/agent/evidence-records",
            {
                "task_id": "task-1",
                "source_url": "https://example.com",
                "source_type": "private_database",
                "source_tool": "agent",
                "snippet": "Example evidence",
                "credibility": 0.7,
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("source_type is invalid" in error for error in payload["errors"]))

    def test_agent_http_rejects_confirmed_fact_without_evidence_ids(self):
        status, payload = _post_json_expect_error(
            "/api/agent/facts",
            {
                "task_id": "task-1",
                "statement": "Example LLC operates example.com.",
                "subject": "Example LLC",
                "predicate": "has_domain",
                "object": "example.com",
                "status": "CONFIRMED",
                "confidence": 0.8,
                "admiralty_code": "A-2",
                "evidence_ids": [],
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("evidence_ids is required for confirmed or likely facts" in error for error in payload["errors"]))

    def test_agent_http_rejects_invalid_relationship_payload(self):
        status, payload = _post_json_expect_error(
            "/api/agent/relationships",
            {"task_id": "task-1", "from": "Example LLC", "to": "", "relationship_type": "", "confidence": -0.1},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("to is required" in error for error in payload["errors"]))
        self.assertTrue(any("relationship_type is required" in error for error in payload["errors"]))
        self.assertTrue(any("confidence must be between 0 and 1" in error for error in payload["errors"]))
```

Add this helper near `_post_json` helpers:

```python
def _post_json_expect_error(path: str, payload: dict) -> tuple[int, dict]:
    memory_store = MemoryStore()
    original_store = app_main.store
    app_main.store = memory_store
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = Request(
            f"{base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            response = exc.fp
            return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        app_main.store = original_store
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol
```

Expected: new tests fail because invalid payloads are accepted or crash through existing handlers.

---

### Task 2: Implement Payload Validator

**Files:**
- Create: `backend/app/core/agent_payload_validation.py`

- [ ] **Step 1: Add validation module**

Create `backend/app/core/agent_payload_validation.py`:

```python
from __future__ import annotations

from typing import Any

from app.core.fact_pool import FACT_STATUSES


SOURCE_TYPES = {
    "official_website",
    "government_registry",
    "regulatory_filing",
    "original_social_profile",
    "mainstream_media",
    "industry_association",
    "business_directory",
    "job_board",
    "map_listing",
    "search_result",
    "aggregator",
    "tool_output",
    "single_weak_signal",
    "anonymous_forum",
    "unknown",
}


def validate_agent_payload(kind: str, payload: dict[str, Any]) -> list[str]:
    validators = {
        "entities": _validate_entities,
        "evidence": _validate_evidence,
        "evidence_records": _validate_evidence_record,
        "facts": _validate_fact,
        "relationships": _validate_relationship,
    }
    validator = validators.get(kind)
    if validator is None:
        return [f"unknown payload kind: {kind}"]
    return validator(payload)


def _validate_entities(payload: dict[str, Any]) -> list[str]:
    errors = []
    errors.extend(_require_strings(payload, ["task_id"]))
    entities = payload.get("entities")
    if not isinstance(entities, list) or not entities:
        errors.append("entities must be a non-empty list")
        return errors
    for index, item in enumerate(entities):
        prefix = f"entities[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        errors.extend(_require_strings(item, ["type", "value", "source_tool"], prefix=prefix))
        errors.extend(_number_between(item, "confidence", prefix=prefix))
    return errors


def _validate_evidence(payload: dict[str, Any]) -> list[str]:
    return _require_strings(payload, ["task_id", "entity_value", "evidence_kind", "source_tool", "snippet"])


def _validate_evidence_record(payload: dict[str, Any]) -> list[str]:
    errors = _require_strings(payload, ["task_id", "source_url", "source_type", "source_tool", "snippet"])
    source_type = payload.get("source_type")
    if isinstance(source_type, str) and source_type.strip() and source_type not in SOURCE_TYPES:
        errors.append("source_type is invalid")
    errors.extend(_number_between(payload, "credibility"))
    return errors


def _validate_fact(payload: dict[str, Any]) -> list[str]:
    errors = _require_strings(payload, ["task_id", "statement", "subject", "predicate", "object", "status"])
    status = payload.get("status")
    if isinstance(status, str) and status.strip() and status not in FACT_STATUSES:
        errors.append("status is invalid")
    errors.extend(_number_between(payload, "confidence"))
    if status in {"CONFIRMED", "LIKELY"}:
        if not str(payload.get("admiralty_code") or "").strip():
            errors.append("admiralty_code is required for confirmed or likely facts")
        evidence_ids = payload.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            errors.append("evidence_ids is required for confirmed or likely facts")
    return errors


def _validate_relationship(payload: dict[str, Any]) -> list[str]:
    errors = _require_strings(payload, ["task_id", "from", "to", "relationship_type"])
    errors.extend(_number_between(payload, "confidence"))
    return errors


def _require_strings(payload: dict[str, Any], fields: list[str], prefix: str = "") -> list[str]:
    errors = []
    for field in fields:
        value = payload.get(field)
        label = f"{prefix}.{field}" if prefix else field
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label} is required")
    return errors


def _number_between(payload: dict[str, Any], field: str, prefix: str = "") -> list[str]:
    label = f"{prefix}.{field}" if prefix else field
    try:
        value = float(payload[field])
    except (KeyError, TypeError, ValueError):
        return [f"{label} must be a number"]
    if not 0 <= value <= 1:
        return [f"{label} must be between 0 and 1"]
    return []
```

- [ ] **Step 2: Run focused validator import check**

Run:

```bash
PYTHONPATH=backend python3 - <<'PY'
from app.core.agent_payload_validation import validate_agent_payload
print(validate_agent_payload("facts", {"status": "CONFIRMED"}))
PY
```

Expected: prints a list of validation errors.

---

### Task 3: Wire Validation Into API

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Import validator**

Add near the other core imports:

```python
from app.core.agent_payload_validation import validate_agent_payload
```

- [ ] **Step 2: Add helper method**

Inside `ApiHandler`, near `_read_json`, add:

```python
    def _validation_failed(self, errors: list[str]) -> bool:
        if not errors:
            return False
        self._json({"detail": "validation failed", "errors": errors}, status=400)
        return True
```

- [ ] **Step 3: Validate each selected endpoint**

For `/api/agent/entities`, after `payload = self._read_json()`, add:

```python
            if self._validation_failed(validate_agent_payload("entities", payload)):
                return
```

For `/api/agent/evidence`, after `payload = self._read_json()`, add:

```python
            if self._validation_failed(validate_agent_payload("evidence", payload)):
                return
```

For `/api/agent/evidence-records`, after `payload = self._read_json()`, add:

```python
                if self._validation_failed(validate_agent_payload("evidence_records", payload)):
                    return
```

For `/api/agent/facts`, after `payload = self._read_json()`, add:

```python
                if self._validation_failed(validate_agent_payload("facts", payload)):
                    return
```

For `/api/agent/relationships`, after `payload = self._read_json()`, add:

```python
            if self._validation_failed(validate_agent_payload("relationships", payload)):
                return
```

- [ ] **Step 4: Run agent protocol tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol
```

Expected: all tests pass.

---

### Task 4: Documentation Update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add write-back validation note**

In the `Agent / Skill 治理层` section, add this paragraph after the validation script paragraph:

```markdown
结构化 Agent 写回会在 API 边界做轻量校验：`entities`、`evidence`、`evidence-records`、`facts` 和 `relationships` 必须包含必需字段，置信度必须在 `0..1`，已确认事实必须带证据 ID 和 Admiralty Code。校验失败会返回 `400` 和错误列表。
```

- [ ] **Step 2: Check README contains the note**

Run:

```bash
rg -n "结构化 Agent 写回|Admiralty Code" README.md
```

Expected: the new note is present.

---

### Task 5: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run agent protocol tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol
```

Expected: all tests pass.

- [ ] **Step 2: Run governance validator**

Run:

```bash
python3 scripts/check_agents.py
```

Expected: `OK - agent governance manifest is valid.`

- [ ] **Step 3: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: existing project verification passes.

---

## Self-Review

- Spec coverage: selected endpoints, rules, error response, docs, and verification are covered.
- Runtime safety: only selected structured write endpoints are changed; task completion and hypotheses remain unchanged.
- Type consistency: validator kind names match API call sites.
- TDD: HTTP rejection tests are written before implementation.
