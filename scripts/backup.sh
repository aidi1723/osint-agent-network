#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

BACKUP_ROOT="${BACKUP_ROOT:-/home/aidi/backups/osint-agent-network}"
BACKUP_KEEP_LAST="${BACKUP_KEEP_LAST:-14}"
if [[ "$BACKUP_ROOT" == /home/aidi/* && ! -d /home/aidi ]]; then
  BACKUP_ROOT="$ROOT_DIR/data/backups"
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$BACKUP_DIR"

copy_if_present() {
  local source="$1"
  local target="$2"
  if [[ -e "$source" ]]; then
    cp -a "$source" "$target"
  fi
}

copy_if_present "$ROOT_DIR/data" "$BACKUP_DIR/data"
copy_if_present "$ROOT_DIR/reports" "$BACKUP_DIR/reports"
copy_if_present "$ROOT_DIR/.env" "$BACKUP_DIR/env.snapshot"

if [[ -f "$BACKUP_DIR/env.snapshot" ]]; then
  chmod 600 "$BACKUP_DIR/env.snapshot"
fi

find "$BACKUP_DIR" -maxdepth 2 -type f | sort > "$BACKUP_DIR/manifest.txt"

prune_old_backups() {
  local keep_last="$1"
  if ! [[ "$keep_last" =~ ^[0-9]+$ ]]; then
    echo "invalid BACKUP_KEEP_LAST=$keep_last" >&2
    exit 1
  fi
  if (( keep_last < 1 )); then
    echo "BACKUP_KEEP_LAST must be >= 1" >&2
    exit 1
  fi
  local backups=()
  while IFS= read -r path; do
    backups+=("$path")
  done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20??????-??????' | sort)
  local total="${#backups[@]}"
  local remove_count=$(( total - keep_last ))
  if (( remove_count <= 0 )); then
    return
  fi
  local index=0
  while (( index < remove_count )); do
    rm -rf "${backups[$index]}"
    index=$(( index + 1 ))
  done
}

prune_old_backups "$BACKUP_KEEP_LAST"

echo "backup_dir=$BACKUP_DIR"
echo "manifest=$BACKUP_DIR/manifest.txt"
echo "keep_last=$BACKUP_KEEP_LAST"
