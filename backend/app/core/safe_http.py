from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import re
import socket
import ssl
from typing import Callable, Mapping
from urllib.parse import urljoin, urlsplit


class SafeHttpError(RuntimeError):
    pass


class InvalidHttpTarget(SafeHttpError):
    pass


class BlockedNetworkTarget(SafeHttpError):
    pass


class RedirectLimitExceeded(SafeHttpError):
    pass


class ResponseTooLarge(SafeHttpError):
    pass


@dataclass(frozen=True)
class ValidatedTarget:
    scheme: str
    original_hostname: str
    validated_ips: tuple[str, ...]
    port: int
    request_path: str

    @property
    def hostname(self) -> str:
        return self.original_hostname


@dataclass(frozen=True)
class SafeHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str


Resolver = Callable[..., list[tuple]]
Connector = Callable[[ValidatedTarget, float, Mapping[str, str]], tuple[object, object]]
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def validate_public_url(url: str, resolver: Resolver = socket.getaddrinfo) -> ValidatedTarget:
    if not isinstance(url, str) or not url or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        raise InvalidHttpTarget("invalid HTTP target")
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except (TypeError, ValueError):
        raise InvalidHttpTarget("invalid HTTP target") from None

    if scheme not in {"http", "https"} or not hostname:
        raise InvalidHttpTarget("invalid HTTP target")
    if username is not None or password is not None or "#" in url:
        raise InvalidHttpTarget("invalid HTTP target")
    if "%" in hostname:
        raise InvalidHttpTarget("invalid HTTP target")

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        raise InvalidHttpTarget("invalid HTTP target") from None
    if not ascii_hostname or not _valid_hostname(ascii_hostname):
        raise InvalidHttpTarget("invalid HTTP target")

    port = port if port is not None else (443 if scheme == "https" else 80)
    if port not in {80, 443}:
        raise InvalidHttpTarget("invalid HTTP target")

    literal_address = _literal_address(ascii_hostname)
    if literal_address is not None:
        addresses = {literal_address}
    else:
        addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        try:
            answers = resolver(ascii_hostname, port, type=socket.SOCK_STREAM)
            for answer in answers:
                addresses.add(ipaddress.ip_address(answer[4][0]))
        except (IndexError, KeyError, OSError, TypeError, ValueError):
            raise InvalidHttpTarget("target resolution failed") from None
    if not addresses:
        raise InvalidHttpTarget("target resolution failed")
    if any(not _is_global_address(address) for address in addresses):
        raise BlockedNetworkTarget("network target is blocked")

    ordered = tuple(str(address) for address in sorted(addresses, key=lambda item: (item.version, int(item))))
    request_path = parsed.path or "/"
    if parsed.query:
        request_path = f"{request_path}?{parsed.query}"
    return ValidatedTarget(scheme, ascii_hostname, ordered, port, request_path)


def safe_fetch(
    url: str,
    timeout_seconds: float,
    max_bytes: int,
    max_redirects: int = 5,
    resolver: Resolver = socket.getaddrinfo,
    connector: Connector | None = None,
    headers: Mapping[str, str] | None = None,
) -> SafeHttpResponse:
    if max_bytes < 0 or max_redirects < 0 or timeout_seconds <= 0:
        raise ValueError("safe_fetch limits must be positive")
    connector = connector or connect_pinned
    base_headers = _validated_headers(headers)
    current_url = url
    redirects = 0

    while True:
        target = validate_public_url(current_url, resolver=resolver)
        request_headers = dict(base_headers)
        request_headers["Host"] = _host_header(target)
        response = None
        connection = None
        try:
            try:
                response, connection = connector(target, timeout_seconds, request_headers)
            except SafeHttpError:
                raise
            except (OSError, TimeoutError, ValueError, http.client.HTTPException):
                raise SafeHttpError("HTTP fetch failed") from None

            status = int(getattr(response, "status", 0) or 0)
            response_headers = _copy_headers(getattr(response, "headers", {}))
            if status in _REDIRECT_STATUSES:
                location = _header(response_headers, "Location")
                if not location:
                    raise InvalidHttpTarget("invalid redirect location")
                if redirects >= max_redirects:
                    raise RedirectLimitExceeded("redirect limit exceeded")
                next_url = urljoin(_canonical_url(target), location)
                current_url = next_url
                redirects += 1
                continue

            try:
                body = response.read(max_bytes + 1)
            except (OSError, TimeoutError, http.client.HTTPException):
                raise SafeHttpError("HTTP fetch failed") from None
            if len(body) > max_bytes:
                raise ResponseTooLarge("HTTP response exceeded size limit")
            return SafeHttpResponse(status, response_headers, body, _canonical_url(target))
        finally:
            _close(response)
            if connection is not response:
                _close(connection)


def connect_pinned(
    target: ValidatedTarget,
    timeout_seconds: float,
    headers: Mapping[str, str],
) -> tuple[http.client.HTTPResponse, http.client.HTTPConnection]:
    last_error: BaseException | None = None
    for address in target.validated_ips:
        raw_socket = None
        connection = None
        succeeded = False
        try:
            connection = http.client.HTTPConnection(target.original_hostname, target.port, timeout=timeout_seconds)
            raw_socket = socket.create_connection((address, target.port), timeout=timeout_seconds)
            if target.scheme == "https":
                raw_socket = ssl.create_default_context().wrap_socket(
                    raw_socket,
                    server_hostname=target.original_hostname,
                )
            connection.sock = raw_socket
            connection.request("GET", target.request_path, headers=dict(headers))
            response = connection.getresponse()
            succeeded = True
            return response, connection
        except (OSError, TimeoutError, ValueError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            if not succeeded:
                _close(connection)
                _close(raw_socket)
    if last_error is None:
        raise OSError("no validated address available")
    raise SafeHttpError("HTTP fetch failed") from None


def _is_global_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return _is_global_address(address.ipv4_mapped)
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


def _literal_address(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(hostname))
    except OSError:
        return None


def _valid_hostname(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if len(hostname) > 253:
        return False
    labels = hostname.split(".")
    return all(
        label
        and len(label) <= 63
        and label[0] != "-"
        and label[-1] != "-"
        and all(char.isalnum() or char == "-" for char in label)
        for label in labels
    )


def _host_header(target: ValidatedTarget) -> str:
    host = f"[{target.original_hostname}]" if ":" in target.original_hostname else target.original_hostname
    default_port = 443 if target.scheme == "https" else 80
    return host if target.port == default_port else f"{host}:{target.port}"


def _canonical_url(target: ValidatedTarget) -> str:
    return f"{target.scheme}://{_host_header(target)}{target.request_path}"


def _validated_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise InvalidHttpTarget("invalid HTTP headers")
    validated = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise InvalidHttpTarget("invalid HTTP headers")
        if not _HEADER_NAME_RE.fullmatch(name):
            raise InvalidHttpTarget("invalid HTTP headers")
        if any(ord(char) < 32 or ord(char) == 127 or ord(char) > 255 for char in value):
            raise InvalidHttpTarget("invalid HTTP headers")
        if name.lower() != "host":
            validated[name] = value
    return validated


def _copy_headers(headers: object) -> dict[str, str]:
    if hasattr(headers, "items"):
        return {str(key): str(value) for key, value in headers.items()}
    return {}


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def _close(resource: object | None) -> None:
    close = getattr(resource, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass
