import hashlib
import secrets


AGENT_ROLE_TIERS = frozenset({"reader", "verifier", "reporter", "tool_agent"})
MAX_AGENT_NAME_LENGTH = 128
MAX_AGENT_TYPE_LENGTH = 128
MAX_AGENT_CAPABILITIES = 64
MAX_AGENT_CAPABILITY_LENGTH = 128


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
