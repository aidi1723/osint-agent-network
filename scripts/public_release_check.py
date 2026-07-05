from __future__ import annotations

import json
from pathlib import Path


REQUIRED_LICENSE_ID = "GPL-3.0-only"
GPLV3_TEXT_MARKERS = (
    "GNU GENERAL PUBLIC LICENSE",
    "Version 3, 29 June 2007",
    "Everyone is permitted to copy and distribute verbatim copies",
    "END OF TERMS AND CONDITIONS",
)


def evaluate_public_release(root: Path) -> dict:
    license_text = _read_text(root / "LICENSE")
    package_license = _package_license(root / "frontend" / "package.json")
    detected_license = _detect_license_text(license_text)
    checks = {
        "license_file": "ok" if detected_license == REQUIRED_LICENSE_ID else "fail",
        "package_license": "ok" if package_license == REQUIRED_LICENSE_ID else "fail",
        "license_consistency": "ok" if detected_license == package_license == REQUIRED_LICENSE_ID else "fail",
    }
    blockers = []
    if checks["license_file"] != "ok":
        blockers.append("LICENSE must contain the full GNU GPL v3 license text.")
    if checks["package_license"] != "ok":
        blockers.append("frontend/package.json license must be GPL-3.0-only.")
    if checks["license_consistency"] != "ok":
        blockers.append("LICENSE text and frontend/package.json metadata must both use GPL-3.0-only.")
    return {
        "ready": not blockers,
        "checks": checks,
        "detected_license": detected_license,
        "package_license": package_license,
        "blockers": blockers,
    }


def _detect_license_text(text: str) -> str:
    if all(marker in text for marker in GPLV3_TEXT_MARKERS):
        return REQUIRED_LICENSE_ID
    return ""


def _package_license(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("license") or "").strip()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = evaluate_public_release(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
