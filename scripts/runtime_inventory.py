from __future__ import annotations

import json
from pathlib import Path


RUNTIME_PATHS = [
    "data/*.sqlite",
    "data/*.sqlite-*",
    "data/*.log",
    "data/*.pid",
    "data/jobs",
    "data/artifacts",
    "data/snapshots",
    "data/screenshots",
    "reports",
    "output",
    "frontend/dist",
]


def build_runtime_inventory(root: Path) -> dict:
    inventory = {}
    for pattern in RUNTIME_PATHS:
        matches = sorted(root.glob(pattern))
        if not matches:
            inventory[pattern] = {"present": False, "files": 0, "directories": 0, "bytes": 0}
            continue
        files = 0
        directories = 0
        total_bytes = 0
        for path in matches:
            if path.is_file():
                files += 1
                total_bytes += path.stat().st_size
                continue
            if path.is_dir():
                directories += 1
                for child in path.rglob("*"):
                    if child.is_dir():
                        directories += 1
                    elif child.is_file():
                        files += 1
                        total_bytes += child.stat().st_size
        inventory[pattern] = {
            "present": True,
            "files": files,
            "directories": directories,
            "bytes": total_bytes,
        }
    return inventory


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(build_runtime_inventory(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
