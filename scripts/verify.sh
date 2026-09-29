#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"
PYTHONPATH=backend python3 -m unittest \
  backend.tests.test_core \
  backend.tests.test_agent_protocol \
  backend.tests.test_worker \
  backend.tests.test_graph \
  backend.tests.test_intelligence_requirements \
  backend.tests.test_cross_verification \
  backend.tests.test_intelligence_core_v3 \
  backend.tests.test_quality_gate \
  backend.tests.test_system_status \
  backend.tests.test_tool_health \
  backend.tests.test_regression_smoke \
  backend.tests.test_production_readiness

python3 scripts/regression_smoke.py

cd "$ROOT_DIR/frontend"
npm run check:ui-copy
node --experimental-strip-types ./scripts/test-ui-state.ts
node --experimental-strip-types ./scripts/test-graph-helpers.ts
node --experimental-strip-types ./scripts/test-investigation-bundle.ts
node --experimental-strip-types ./scripts/test-sparse-lead.ts
node --experimental-strip-types ./scripts/test-core-v3.ts
node --experimental-strip-types ./scripts/test-system-status.ts
node --experimental-strip-types ./scripts/test-vite-config.ts
npm run build
