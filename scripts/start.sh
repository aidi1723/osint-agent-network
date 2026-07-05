#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT_DIR/data"
API_PID="$DATA_DIR/api.pid"
WEB_PID="$DATA_DIR/web.pid"
API_LOG="$DATA_DIR/api.log"
WEB_LOG="$DATA_DIR/web.log"

mkdir -p "$DATA_DIR"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

APP_PORT="${APP_PORT:-8088}"
WEB_PORT="${WEB_PORT:-3008}"
STARTUP_TIMEOUT_SECONDS="${STARTUP_TIMEOUT_SECONDS:-30}"

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local log_file="$3"
  local deadline=$((SECONDS + STARTUP_TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name ready: $url"
      return
    fi
    sleep 1
  done
  echo "$name did not become ready within ${STARTUP_TIMEOUT_SECONDS}s: $url" >&2
  if [[ -f "$log_file" ]]; then
    tail -n 40 "$log_file" >&2
  fi
  exit 1
}

if is_running "$API_PID"; then
  echo "api already running: $(cat "$API_PID")"
else
  cd "$ROOT_DIR"
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
  nohup bash -lc "cd '$ROOT_DIR' && exec env PYTHONPATH=backend '$PYTHON_BIN' -m app.main" > "$API_LOG" 2>&1 &
  echo $! > "$API_PID"
  echo "api started: $(cat "$API_PID")"
fi

wait_for_http "api" "http://127.0.0.1:$APP_PORT/api/health" "$API_LOG"

if is_running "$WEB_PID"; then
  echo "web already running: $(cat "$WEB_PID")"
else
  cd "$ROOT_DIR/frontend"
  nohup bash -lc "cd '$ROOT_DIR/frontend' && exec npm run dev -- --host 0.0.0.0 --port '$WEB_PORT'" > "$WEB_LOG" 2>&1 &
  echo $! > "$WEB_PID"
  echo "web started: $(cat "$WEB_PID")"
fi

wait_for_http "web" "http://127.0.0.1:$WEB_PORT/" "$WEB_LOG"

echo "api: http://0.0.0.0:$APP_PORT"
echo "web: http://0.0.0.0:$WEB_PORT"
