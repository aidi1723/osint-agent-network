import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit


class NormalizationError(ValueError):
    pass


_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)
_PRIVATE_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def normalize_target(target_type: str, value: str) -> str:
    raw = value.strip()
    if not raw:
        raise NormalizationError("target value is empty")

    if target_type in {"domain", "subdomain"}:
        normalized = raw.rstrip(".").lower()
        if not _DOMAIN_RE.match(normalized):
            raise NormalizationError(f"invalid {target_type}: {value}")
        return normalized

    if target_type == "email":
        normalized = raw.lower()
        if normalized.count("@") != 1:
            raise NormalizationError(f"invalid email: {value}")
        local, domain = normalized.split("@", 1)
        if not local or not _DOMAIN_RE.match(domain):
            raise NormalizationError(f"invalid email: {value}")
        return normalized

    if target_type == "username":
        if not _USERNAME_RE.match(raw):
            raise NormalizationError(f"invalid username: {value}")
        return raw

    if target_type == "phone":
        compact = re.sub(r"[\s().-]+", "", raw)
        if not compact.startswith("+"):
            raise NormalizationError("phone targets must use E.164 format with country code")
        digits = compact[1:]
        if not digits.isdigit() or not 8 <= len(digits) <= 15:
            raise NormalizationError(f"invalid phone: {value}")
        return f"+{digits}"

    if target_type == "ip":
        return raw

    if target_type in {"company", "sparse_lead"}:
        normalized = re.sub(r"\s+", " ", raw)
        if len(normalized) > 500:
            raise NormalizationError(f"{target_type} target is too long: {value}")
        return normalized

    if target_type in {"url", "profile_url"}:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise NormalizationError(f"invalid {target_type}: {value}")
        hostname = (parsed.hostname or "").lower()
        if hostname in _PRIVATE_HOSTS or hostname.endswith(".local"):
            raise NormalizationError(f"private {target_type}: {value}")
        try:
            literal_address = ipaddress.ip_address(hostname)
        except ValueError:
            literal_address = _legacy_ipv4_address(hostname)
        if literal_address is not None and not _is_public_address(literal_address):
            raise NormalizationError(f"private {target_type}: {value}")
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path or "/",
                "",
                "",
            )
        )

    raise NormalizationError(f"unsupported target type: {target_type}")


def _legacy_ipv4_address(hostname: str) -> ipaddress.IPv4Address | None:
    if not hostname or any(char not in "0123456789." for char in hostname):
        return None
    try:
        return ipaddress.IPv4Address(socket.inet_aton(hostname))
    except OSError:
        return None


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return _is_public_address(address.ipv4_mapped)
    return address.is_global and not any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )
