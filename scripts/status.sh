#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT_DIR/data"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

APP_PORT="${APP_PORT:-8088}"
WEB_PORT="${WEB_PORT:-3008}"

show_pid() {
  local name="$1"
  local pid_file="$2"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$name running: $(cat "$pid_file")"
  else
    echo "$name not running"
  fi
}

show_pid "api" "$DATA_DIR/api.pid"
show_pid "web" "$DATA_DIR/web.pid"

lsof -iTCP:"$APP_PORT" -sTCP:LISTEN -n -P 2>/dev/null || true
lsof -iTCP:"$WEB_PORT" -sTCP:LISTEN -n -P 2>/dev/null || true
