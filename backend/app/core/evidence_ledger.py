from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from urllib.parse import urlsplit, urlunsplit

from app.core.verification import admiralty_code


@dataclass(frozen=True)
class EvidenceLedgerRecord:
    id: str
    investigation_id: str
    source_url: str
    source_type: str
    source_tool: str
    snippet: str
    observed_at: str
    admiralty_code: str
    source_reliability: str
    information_credibility: str
    content_hash: str


def build_evidence_record(
    id: str,
    investigation_id: str,
    source_url: str,
    source_type: str,
    source_tool: str,
    snippet: str,
    observed_at: str,
    credibility: float,
) -> EvidenceLedgerRecord:
    code = admiralty_code(source_type, credibility)
    return EvidenceLedgerRecord(
        id=id,
        investigation_id=investigation_id,
        source_url=source_url,
        source_type=source_type,
        source_tool=source_tool,
        snippet=snippet,
        observed_at=observed_at,
        admiralty_code=code["code"],
        source_reliability=code["source_reliability"],
        information_credibility=code["information_credibility"],
        content_hash=sha1(f"{_canonical_source_url(source_url)}:{snippet}".encode("utf-8")).hexdigest()[:16],
    )


def _canonical_source_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value.strip()
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))
