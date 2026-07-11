# Reliability Maintenance Guide - 2026-07-02

## Purpose

Use this guide when maintaining the supply-chain and intelligence aggregation features. It explains how to tell real no-findings results from system failures, which tests protect the current behavior, and what to check before deployment.

## Health Checks

Run from the project root:

```bash
bash scripts/verify.sh
```

For a faster targeted check after touching customs or aggregation code:

```bash
PYTHONPATH=backend python3 -m unittest \
  backend.tests.test_customs_supply_chain \
  backend.tests.test_intelligence_aggregation \
  backend.tests.test_customs_api_route
```

For frontend request/error handling:

```bash
cd frontend
npm test
npm run build
```

## Expected Runtime Semantics

### Supply-chain endpoint

Endpoint:

```text
POST /api/customs/supply-chain
```

Interpret responses this way:

- `200` with `downstream.total_count = 0` and `upstream.total_count = 0`: request completed; no partners found in returned customs data.
- `401`: missing or wrong management token.
- `503`: customs API configuration is missing, commonly `UPKUAJING_AUTHORIZATION`.
- `502`: upstream customs API returned an error or could not be reached.
- `504`: upstream customs API timed out.

Do not treat non-2xx responses as intelligence no-findings.

### Intelligence endpoint

Endpoint:

```text
GET /api/investigations/{id}/intelligence
```

The endpoint aggregates existing investigation records only. It does not call external tools. If data is missing:

- Check whether entities/evidence/relationships exist on the investigation.
- Check whether customs products are present as `trade_relationship` evidence.
- Check whether social metadata is linked with `profile_has_*` relationships.

## Common Failure Modes

### Supply-chain panel says credentials are missing

Check:

```bash
grep -E 'UPKUAJING_AUTHORIZATION|ADMIN_API_TOKEN' .env
```

Expected:

- `UPKUAJING_AUTHORIZATION` is present and non-empty on the backend host.
- `ADMIN_API_TOKEN` is present on the backend.
- The browser has an authenticated administrator session; no management credential is present in the frontend build environment.

Do not paste real token values into reports or screenshots.

### Product intelligence is empty

Check the investigation detail JSON for evidence like:

```json
{
  "evidence_kind": "trade_relationship",
  "source_tool": "customs_supply_chain",
  "snippet": "海关记录显示3次交易，产品：Aluminum Profiles, Steel Parts..."
}
```

If products are stored only in an ad hoc payload and not in evidence or `customs_data`, the aggregation endpoint cannot see them.

### Social profile metadata is missing

Check relationships like:

```json
{
  "from_value": "https://github.com/admin",
  "to_value": "Singapore",
  "relationship_type": "profile_has_declared_location"
}
```

Supported relationship metadata:

- `profile_has_bio_snippet`
- `profile_has_declared_location`
- `profile_has_profile_image_url`
- `profile_has_external_link`

## Deployment Checklist

- Run `bash scripts/verify.sh`.
- Confirm `npm run build` has no CSS syntax warnings.
- Confirm `.env` contains backend-only customs credentials.
- Confirm frontend build has the correct API base URL and management token when auth is enabled.
- Confirm `frontend.zip`, `frontend/dist/`, `data/*.sqlite`, `data/*.log`, and `data/*.pid` are not included in source-control handoff artifacts.

## Regression Tests To Preserve

Keep these tests in the verification path:

- `backend.tests.test_customs_supply_chain`
- `backend.tests.test_customs_api_route`
- `backend.tests.test_intelligence_aggregation`
- `frontend/src/api.test.ts`

If one of these tests needs to change, update the corresponding runtime semantics in this document in the same change.
