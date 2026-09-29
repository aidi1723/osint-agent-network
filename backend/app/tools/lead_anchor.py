from __future__ import annotations

from pathlib import Path

from app.core.sparse_lead import anchors_from_metadata
from app.tools.base import ParsedToolOutput, ToolCommand, ToolRunResult, read_json_artifact, write_json_artifact


class LeadAnchorAdapter:
    name = "lead_anchor_extraction"

    def run(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int,
        metadata: dict | None = None,
    ):
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / "lead_anchors.json"
        write_json_artifact(
            artifact,
            {
                "target_type": target_type,
                "target_value": target_value,
                "metadata": metadata or {},
            },
        )
        return ToolRunResult(
            command=ToolCommand(
                args=["lead_anchor_extraction", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="lead anchors extracted",
            stderr_excerpt="",
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        payload = read_json_artifact(artifact_path)
        bundle = anchors_from_metadata(target_value, payload.get("metadata", {}))
        return ParsedToolOutput(
            tool=self.name,
            target_type=payload.get("target_type", "sparse_lead"),
            target_value=target_value,
            entities=bundle.entities,
            evidence=bundle.evidence,
            relationships=bundle.relationships,
        )
