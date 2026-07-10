import hashlib
import hmac
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


AGENT_ROLE_TIERS = frozenset({"reader", "verifier", "reporter", "tool_agent"})
MAX_AGENT_NAME_LENGTH = 128
MAX_AGENT_TYPE_LENGTH = 128
MAX_AGENT_CAPABILITIES = 64
MAX_AGENT_CAPABILITY_LENGTH = 128


@dataclass(frozen=True)
class AgentPrincipal:
    agent_id: str
    role_tier: str
    capabilities: Sequence[str]


AGENT_ACTION_TIERS = {
    "entities": {"reader"},
    "evidence": {"reader"},
    "evidence_records": {"reader"},
    "relationships": {"reader"},
    "facts": {"verifier"},
    "hypotheses": {"verifier"},
    "score_hypotheses": {"verifier"},
    "complete_task": {"reporter"},
}

AGENT_ACTION_OUTPUTS = {
    "entities": "entities",
    "evidence": "evidence",
    "evidence_records": "evidence",
    "relationships": "relationships",
    "facts": "claims",
    "hypotheses": "claims",
    "score_hypotheses": "claims",
    "complete_task": "report",
}


def agent_principal_from_record(record: object) -> AgentPrincipal | None:
    if not isinstance(record, Mapping):
        return None
    agent_id = record.get("id")
    role_tier = record.get("role_tier")
    capabilities = record.get("capabilities")
    if (
        not isinstance(agent_id, str)
        or not agent_id
        or role_tier not in AGENT_ROLE_TIERS
        or not isinstance(capabilities, list)
        or record.get("disabled_at") is not None
    ):
        return None
    return AgentPrincipal(agent_id, role_tier, tuple(capabilities))


def agent_action_allowed(principal: AgentPrincipal, action: str) -> bool:
    return principal.role_tier in AGENT_ACTION_TIERS.get(action, set())


def agent_output_contract_allows(output_contract: object, action: str) -> bool:
    if action == "event":
        return True
    required_output = AGENT_ACTION_OUTPUTS.get(action)
    if required_output is None or not isinstance(output_contract, str):
        return False
    return required_output in agent_output_contract_sections(output_contract)


def agent_output_contract_sections(output_contract: object) -> frozenset[str]:
    if not isinstance(output_contract, str):
        return frozenset()
    return frozenset(
        item.strip()
        for item in output_contract.split(":", 1)[0].split(",")
        if item.strip()
    )


def legacy_agent_token_allowed(env: Mapping[str, str]) -> bool:
    return str(env.get("OSINT_ALLOW_LEGACY_AGENT_TOKEN", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def legacy_agent_token_matches(supplied_token: str, expected_token: str) -> bool:
    if not expected_token:
        return False
    supplied_digest = hashlib.sha256(
        supplied_token.encode("utf-8", errors="surrogatepass")
    ).digest()
    expected_digest = hashlib.sha256(
        expected_token.encode("utf-8", errors="surrogatepass")
    ).digest()
    return hmac.compare_digest(supplied_digest, expected_digest)


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_agent_token() -> str:
    return secrets.token_urlsafe(32)


def validate_agent_role_tier(role_tier: object) -> str:
    if not isinstance(role_tier, str) or role_tier not in AGENT_ROLE_TIERS:
        raise ValueError("invalid agent role tier")
    return role_tier


def validate_agent_registration(
    agent_name: object,
    agent_type: object,
    capabilities: object,
) -> tuple[str, str, list[str]]:
    validated_name = _validate_identity_field(
        agent_name, "invalid agent name", MAX_AGENT_NAME_LENGTH
    )
    validated_type = _validate_identity_field(
        agent_type, "invalid agent type", MAX_AGENT_TYPE_LENGTH
    )
    if not isinstance(capabilities, list) or len(capabilities) > MAX_AGENT_CAPABILITIES:
        raise ValueError("invalid agent capabilities")
    if any(
        not isinstance(item, str)
        or not item
        or item != item.strip()
        or len(item) > MAX_AGENT_CAPABILITY_LENGTH
        or not _is_strict_utf8(item)
        for item in capabilities
    ):
        raise ValueError("invalid agent capabilities")
    return validated_name, validated_type, list(capabilities)


def _validate_identity_field(value: object, error: str, maximum_length: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum_length
        or not _is_strict_utf8(value)
    ):
        raise ValueError(error)
    return value


def _is_strict_utf8(value: str) -> bool:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


class AgentRegistration(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __repr__(self) -> str:
        redacted = dict(self)
        if "agent_token" in redacted:
            redacted["agent_token"] = "<redacted>"
        return repr(redacted)

    __str__ = __repr__
