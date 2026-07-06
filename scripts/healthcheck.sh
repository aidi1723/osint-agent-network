#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

APP_PORT="${APP_PORT:-8088}"
WEB_PORT="${WEB_PORT:-3008}"
API_URL="${API_URL:-http://127.0.0.1:$APP_PORT}"
WEB_URL="${WEB_URL:-http://127.0.0.1:$WEB_PORT}"
READ_TOKEN="${READ_API_TOKEN:-${ADMIN_API_TOKEN:-${AGENT_API_TOKEN:-}}}"

api_health="$(curl -fsS "$API_URL/api/health")"
if [[ -n "$READ_TOKEN" ]]; then
  system_status="$(curl -fsS -H "Authorization: Bearer $READ_TOKEN" "$API_URL/api/system/status")"
else
  system_status="$(curl -fsS "$API_URL/api/system/status")"
fi
web_head="$(curl -fsS "$WEB_URL/" | head -n 5)"

python3 - "$api_health" "$system_status" <<'PY'
import json
import sys

health = json.loads(sys.argv[1])
status = json.loads(sys.argv[2])

if health.get("status") != "ok":
    raise SystemExit("api health is not ok")
if status.get("database", {}).get("status") != "ok":
    raise SystemExit("database status is not ok")
if not status.get("scripts", {}).get("backup", {}).get("present"):
    raise SystemExit("backup script is missing")
print("api=ok")
print("database=ok")
print(f"schema_versions={status.get('database', {}).get('schema_version_count', 0)}")
print(f"investigations={status.get('investigations', {}).get('total', 0)}")
PY

if ! grep -qi "<!doctype html>" <<<"$web_head"; then
  echo "web health is not ok" >&2
  exit 1
fi

echo "web=ok"
