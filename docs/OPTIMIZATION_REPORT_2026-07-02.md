# Optimization Report - 2026-07-02

## Scope

This pass fixes the reliability issues found during the project audit after the previous optimization. It keeps the existing architecture, routes, UI layout, and business workflow intact.

## Fixed Issues

### 1. Customs supply-chain errors are no longer hidden

Before this update, `CustomsSupplyChainAdapter` returned empty lists when the Upkuajing customs client raised configuration, timeout, or upstream errors. The UI then displayed a normal no-data state.

Now:

- `find_downstream_customers()` and `find_upstream_suppliers()` propagate `UpkuajingCustomsError`.
- `POST /api/customs/supply-chain` returns the original error payload and status.
- The operator can distinguish credential/upstream failure from a legitimate no-findings result.

### 2. Product intelligence consumes customs relationship evidence

Before this update, product aggregation only parsed news-oriented evidence kinds or explicit `customs_data`. The customs supply-chain tool writes `trade_relationship` evidence, so product intelligence could remain empty even when customs products existed.

Now:

- `trade_relationship` snippets such as `产品：Aluminum Profiles, Steel Parts` produce product records.
- Products are categorized through the existing product category classifier.
- Customs-derived product mentions use higher confidence than generic text extraction.

### 3. Social profile metadata follows actual tool output

Before this update, `SocialIntelligenceAggregator` expected metadata evidence to be attached directly to the profile URL. Maigret emits metadata as independent entities linked through `profile_has_*` relationships.

Now:

- `profile_has_bio_snippet` populates `bio`.
- `profile_has_declared_location` populates `location`.
- `profile_has_profile_image_url` populates `avatar_url`.
- `profile_has_external_link` appends external links.

### 4. Frontend panels show backend failures

Before this update, the intelligence panel silently returned nothing on failed reads, and the supply-chain deep-investigation action only logged creation errors.

Now:

- Shared API helpers in `frontend/src/api.ts` handle response parsing and backend error details.
- `SupplyChainPanel` displays query and task-creation errors.
- `IntelligencePanel` displays read failures and keeps a compact empty state.

### 5. CSS and repository hygiene

Before this update, `vite build` succeeded but emitted an esbuild CSS warning because `frontend/src/styles.css` ended with an unexpected `}`.

Now:

- The stray CSS block was removed.
- `.gitignore` also ignores `frontend.zip`, `data/*.log`, and `data/*.pid`.
- `scripts/verify.sh` includes the new aggregation regression tests.

## Tests Added

- `backend/tests/test_intelligence_aggregation.py`
  - Verifies `trade_relationship` evidence contributes product intelligence.
  - Verifies profile metadata entities enrich social profiles through relationships.
- `backend/tests/test_customs_supply_chain.py`
  - Verifies customs API errors are raised instead of converted to empty results.
- `backend/tests/test_customs_api_route.py`
  - Verifies `/api/customs/supply-chain` preserves upstream/configuration status.
- `frontend/src/api.test.ts`
  - Verifies supply-chain, intelligence, and deep-investigation helpers surface backend error details.

## Operator Impact

- A red error banner now means the system could not query or create the requested data.
- An empty partner/product/profile list now more accurately means the request completed but found no usable records.
- Existing API tokens and deployment configuration are unchanged.

## Files Changed

- Backend:
  - `backend/app/tools/customs_supply_chain.py`
  - `backend/app/main.py`
  - `backend/app/core/product_intelligence.py`
  - `backend/app/core/social_intelligence.py`
  - `backend/tests/test_customs_supply_chain.py`
  - `backend/tests/test_customs_api_route.py`
  - `backend/tests/test_intelligence_aggregation.py`
- Frontend:
  - `frontend/src/api.ts`
  - `frontend/src/api.test.ts`
  - `frontend/src/types.ts`
  - `frontend/src/components/SupplyChainPanel.tsx`
  - `frontend/src/components/IntelligencePanel.tsx`
  - `frontend/src/styles.css`
- Maintenance:
  - `scripts/verify.sh`
  - `.gitignore`
  - `docs/UPDATE_LOG.md`
  - `docs/MAINTENANCE_RELIABILITY_2026-07-02.md`

