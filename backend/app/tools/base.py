from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit


MAX_OUTPUT_BYTES = 2 * 1024 * 1024  # 2 MB


@dataclass(frozen=True)
class ToolCommand:
    args: list[str]
    cwd: Path
    expected_artifact: Path
    timeout_seconds: int

    def to_dict(self) -> dict:
        data = asdict(self)
        data["cwd"] = str(self.cwd)
        data["expected_artifact"] = str(self.expected_artifact)
        return data


@dataclass(frozen=True)
class NormalizedEntity:
    type: str
    value: str
    source_tool: str
    confidence: float


@dataclass(frozen=True)
class NormalizedEvidence:
    entity_value: str
    evidence_kind: str
    source_tool: str
    snippet: str


@dataclass(frozen=True)
class NormalizedRelationship:
    from_value: str
    to_value: str
    relationship_type: str
    confidence: float


@dataclass(frozen=True)
class ToolRunResult:
    command: ToolCommand
    returncode: int
    stdout_excerpt: str
    stderr_excerpt: str


@dataclass
class ParsedToolOutput:
    tool: str
    target_type: str
    target_value: str
    entities: list[NormalizedEntity]
    evidence: list[NormalizedEvidence]
    relationships: list[NormalizedRelationship]

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "target_type": self.target_type,
            "target_value": self.target_value,
            "counts": {
                "entities": len(self.entities),
                "evidence": len(self.evidence),
                "relationships": len(self.relationships),
            },
            "entities": [asdict(item) for item in self.entities],
            "evidence": [asdict(item) for item in self.evidence],
            "relationships": [asdict(item) for item in self.relationships],
        }


def read_json_artifact(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_artifact(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_tool_command(command: ToolCommand) -> ToolRunResult:
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            proc = subprocess.Popen(
                command.args,
                cwd=str(command.cwd),
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Command not found: {command.args[0]}") from exc
        try:
            proc.wait(timeout=command.timeout_seconds)
        except subprocess.TimeoutExpired:
            # Kill the entire process group to avoid orphan children
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()
            proc.wait(timeout=5)
        return ToolRunResult(
            command=command,
            returncode=proc.returncode if proc.returncode is not None else -9,
            stdout_excerpt=_read_excerpt(stdout_file, MAX_OUTPUT_BYTES),
            stderr_excerpt=_read_excerpt(stderr_file, MAX_OUTPUT_BYTES),
        )


def append_unique_entity(
    items: list[NormalizedEntity],
    seen: set[tuple[str, str]],
    item: NormalizedEntity,
) -> None:
    key = (item.type, item.value)
    if key not in seen:
        seen.add(key)
        items.append(item)


def append_unique_evidence(
    items: list[NormalizedEvidence],
    seen: set[tuple[str, str, str]],
    item: NormalizedEvidence,
) -> None:
    key = (item.entity_value, item.evidence_kind, item.source_tool)
    if key not in seen:
        seen.add(key)
        items.append(item)


def append_unique_relationship(
    items: list[NormalizedRelationship],
    seen: set[tuple[str, str, str]],
    item: NormalizedRelationship,
) -> None:
    key = (item.from_value, item.to_value, item.relationship_type)
    if key not in seen:
        seen.add(key)
        items.append(item)


def _truncate(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _read_excerpt(file_obj, limit: int) -> str:
    file_obj.seek(0, os.SEEK_END)
    size = file_obj.tell()
    file_obj.seek(0)
    data = file_obj.read(limit)
    text = data.decode("utf-8", errors="replace")
    if size <= limit:
        return text
    return text + "\n...[output limit exceeded]"


def redacted_url(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
