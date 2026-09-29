#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_manifest_validator import validate_repository


def main() -> int:
    errors = validate_repository(ROOT)
    if errors:
        print(f"FAIL - {len(errors)} agent governance issue(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("OK - agent governance manifest is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
