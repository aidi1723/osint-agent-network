#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"
if command -v uv >/dev/null 2>&1 && [ -f backend/uv.lock ]; then
  PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests
elif [ -x backend/.venv/bin/python ]; then
  PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests
else
  PYTHON_BIN=""
  for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
  if [ -z "$PYTHON_BIN" ]; then
    echo "Python 3.11 or newer is required, but no python3 executable was found." >&2
    exit 1
  fi
  if ! "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    echo "Python 3.11 or newer is required, but $PYTHON_BIN is too old." >&2
    exit 1
  fi
  PYTHONPATH=backend "$PYTHON_BIN" -m unittest discover -s backend/tests
fi

python3 scripts/check_agents.py
python3 scripts/regression_smoke.py
python3 scripts/runtime_inventory.py >/dev/null
python3 scripts/public_release_check.py >/dev/null

cd "$ROOT_DIR/frontend"
npm run check:ui-copy
node --experimental-strip-types ./scripts/test-default-investigation.ts
node --experimental-strip-types ./scripts/test-hcs-graph-data.ts
node --experimental-strip-types ./scripts/test-ui-state.ts
node --experimental-strip-types ./scripts/test-graph-helpers.ts
node --experimental-strip-types ./scripts/test-investigation-bundle.ts
node --experimental-strip-types ./scripts/test-sparse-lead.ts
node --experimental-strip-types ./scripts/test-core-v3.ts
node --experimental-strip-types ./scripts/test-system-status.ts
node --experimental-strip-types ./scripts/test-vite-config.ts
node --experimental-strip-types ./scripts/test-intelligence-core-v2.ts
node --experimental-strip-types ./scripts/test-responsive-css.ts
npm test
npm run build
