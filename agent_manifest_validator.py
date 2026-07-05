from __future__ import annotations

import json
from pathlib import Path
from typing import Any


KNOWN_OUTPUT_TOKENS = {
    "entities",
    "evidence",
    "relationships",
    "facts",
    "cross_verification_matrix",
    "quality_notes",
    "report_markdown",
    "directed_collection",
}

KNOWN_TOOL_FAMILIES = {
    "official",
    "registry",
    "directory",
    "news",
    "social",
    "search",
    "tool",
    "operator",
}


def validate_repository(root: Path) -> list[str]:
    root = root.resolve()
    manifest_path = root / "agent-manifest.json"
    if not manifest_path.is_file():
        return ["missing agent-manifest.json"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid manifest JSON: {exc}"]

    errors: list[str] = []
    skills = manifest.get("skills")
    agents = manifest.get("agents")
    if not isinstance(skills, list):
        errors.append("manifest skills must be a list")
        skills = []
    if not isinstance(agents, list):
        errors.append("manifest agents must be a list")
        agents = []

    manifest_skill_names = {
        str(item.get("name"))
        for item in skills
        if isinstance(item, dict) and item.get("name")
    }
    for skill in skills:
        if not isinstance(skill, dict):
            errors.append("manifest skill entry must be an object")
            continue
        errors.extend(_validate_skill(root, skill))

    for agent in agents:
        if not isinstance(agent, dict):
            errors.append("manifest agent entry must be an object")
            continue
        errors.extend(_validate_agent(root, agent, manifest_skill_names))

    return errors


def _validate_skill(root: Path, skill: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    name = str(skill.get("name") or "")
    path_value = str(skill.get("path") or "")
    if not name:
        errors.append("manifest skill missing name")
    if not path_value:
        errors.append(f"manifest skill {name or '<unknown>'} missing path")
        return errors

    path = root / path_value
    if not path.is_file():
        errors.append(f"missing skill file: {path_value}")
        return errors

    frontmatter, fm_errors = parse_frontmatter(path)
    errors.extend(fm_errors)
    if frontmatter.get("name") != name:
        errors.append(f"skill name mismatch for {path_value}: manifest={name} frontmatter={frontmatter.get('name')}")
    for required in ("name", "description"):
        if not frontmatter.get(required):
            errors.append(f"skill frontmatter missing {required}: {path_value}")
    return errors


def _validate_agent(root: Path, agent: dict[str, Any], manifest_skill_names: set[str]) -> list[str]:
    errors: list[str] = []
    name = str(agent.get("name") or "")
    path_value = str(agent.get("path") or "")
    if not name:
        errors.append("manifest agent missing name")
    if not path_value:
        errors.append(f"manifest agent {name or '<unknown>'} missing path")
        return errors

    for token in _contract_tokens(str(agent.get("output_contract") or "")):
        if token not in KNOWN_OUTPUT_TOKENS:
            errors.append(f"invalid output contract token for {name}: {token}")

    for family in agent.get("allowed_tool_families") or []:
        if family not in KNOWN_TOOL_FAMILIES:
            errors.append(f"invalid allowed tool family for {name}: {family}")

    for skill_name in agent.get("skills") or []:
        if skill_name not in manifest_skill_names:
            errors.append(f"unknown manifest skill for {name}: {skill_name}")

    path = root / path_value
    if not path.is_file():
        errors.append(f"missing agent file: {path_value}")
        return errors

    frontmatter, fm_errors = parse_frontmatter(path)
    errors.extend(fm_errors)
    if frontmatter.get("name") != name:
        errors.append(f"agent name mismatch for {path_value}: manifest={name} frontmatter={frontmatter.get('name')}")
    for required in ("name", "description", "skills", "output_contract"):
        if not frontmatter.get(required):
            errors.append(f"agent frontmatter missing {required}: {path_value}")

    for token in _contract_tokens(str(frontmatter.get("output_contract") or "")):
        if token not in KNOWN_OUTPUT_TOKENS:
            errors.append(f"invalid output contract token for {name}: {token}")

    for skill_name in frontmatter.get("skills") or []:
        if skill_name not in manifest_skill_names:
            errors.append(f"unknown frontmatter skill for {name}: {skill_name}")
    return errors


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], list[str]]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, [f"missing frontmatter: {path}"]
    try:
        _, raw, _ = text.split("---", 2)
    except ValueError:
        return {}, [f"unterminated frontmatter: {path}"]

    data: dict[str, Any] = {}
    current_list_key = ""
    for raw_line in raw.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("  - ") and current_list_key:
            data.setdefault(current_list_key, []).append(line[4:].strip())
            continue
        if ":" not in line:
            return {}, [f"invalid frontmatter line in {path}: {line}"]
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            data[key] = value
            current_list_key = ""
        else:
            data[key] = []
            current_list_key = key
    return data, []


def _contract_tokens(value: str) -> list[str]:
    return [token.strip() for token in value.split(",") if token.strip()]
