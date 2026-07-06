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

find_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "$PYTHON_BIN"
    return
  fi

  local candidate
  for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return
    fi
  done

  for candidate in /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 $HOME/.local/bin/python3.11; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return
    fi
  done
}

require_python_version() {
  local python_bin="$1"
  if [[ -z "$python_bin" ]]; then
    echo "Python 3.11 or newer is required, but no python3 executable was found." >&2
    exit 1
  fi
  if ! "$python_bin" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    echo "Python 3.11 or newer is required, but $python_bin is too old." >&2
    exit 1
  fi
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
  PYTHON_BIN="$(find_python_bin)"
  require_python_version "$PYTHON_BIN"
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
