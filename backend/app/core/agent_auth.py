import hashlib
import secrets


AGENT_ROLE_TIERS = frozenset({"reader", "verifier", "reporter", "tool_agent"})


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_agent_token() -> str:
    return secrets.token_urlsafe(32)


def validate_agent_role_tier(role_tier: object) -> str:
    if not isinstance(role_tier, str) or role_tier not in AGENT_ROLE_TIERS:
        raise ValueError("invalid agent role tier")
    return role_tier


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
