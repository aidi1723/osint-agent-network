from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import UTC, datetime
import http.client
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import socket
import ssl
import threading
import time
from typing import Callable, Mapping
from urllib.parse import urljoin, urlsplit


class SafeHttpError(RuntimeError):
    pass


class InvalidHttpTarget(SafeHttpError):
    pass


class BlockedNetworkTarget(SafeHttpError):
    pass


class FakeIpApprovalRequired(BlockedNetworkTarget):
    def __init__(self, hostname: str):
        self.hostname = hostname
        super().__init__("fake-IP host requires review")


class RedirectLimitExceeded(SafeHttpError):
    pass


class ResponseTooLarge(SafeHttpError):
    pass


class InvalidFakeIpConfiguration(SafeHttpError):
    pass


@dataclass(frozen=True)
class FakeIpAllowance:
    networks: tuple[ipaddress.IPv4Network, ...] = ()
    hosts: frozenset[str] = frozenset()
    review_unapproved_hosts: bool = field(default=False, compare=False, repr=False)


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
MAX_RESOLVED_ADDRESSES = 8  # Bound raw DNS fan-out before deduplication.
MAX_VALIDATED_ADDRESSES = 8  # Bound sequential connection failover.
_FAKE_IP_SUPERNET = ipaddress.ip_network("198.18.0.0/15")
_MAX_FAKE_IP_APPROVAL_FILE_BYTES = 64 * 1024
_INVALID_FAKE_IP_CONFIGURATION_MESSAGE = "invalid fake-IP allowance configuration"
_RESOLVER_WORKERS = 4
_RESOLVER_QUEUE: queue.Queue = queue.Queue(maxsize=32)


def fake_ip_allowance_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    now: datetime | None = None,
) -> FakeIpAllowance:
    environ = os.environ if environ is None else environ
    approval_path = str(environ.get("OSINT_SAFE_HTTP_FAKE_IP_APPROVALS_FILE", "")).strip()
    raw_cidrs = str(environ.get("OSINT_SAFE_HTTP_FAKE_IP_CIDRS", "")).strip()
    raw_hosts = str(environ.get("OSINT_SAFE_HTTP_FAKE_IP_HOSTS", "")).strip()
    if approval_path:
        if raw_cidrs or raw_hosts:
            raise _invalid_fake_ip_configuration()
        return _approval_file_allowance(Path(approval_path), now=now)
    return _legacy_fake_ip_allowance(raw_cidrs, raw_hosts)


def _legacy_fake_ip_allowance(raw_cidrs: str, raw_hosts: str) -> FakeIpAllowance:
    if not raw_cidrs and not raw_hosts:
        return FakeIpAllowance()
    if not raw_cidrs or not raw_hosts:
        raise _invalid_fake_ip_configuration()

    networks: list[ipaddress.IPv4Network] = []
    hosts: set[str] = set()
    try:
        for raw_network in _config_items(raw_cidrs):
            network = ipaddress.ip_network(raw_network, strict=True)
            if not isinstance(network, ipaddress.IPv4Network) or not network.subnet_of(_FAKE_IP_SUPERNET):
                raise ValueError
            if network not in networks:
                networks.append(network)
        for raw_host in _config_items(raw_hosts):
            host = raw_host.encode("idna").decode("ascii").lower().rstrip(".")
            if not host or not _valid_hostname(host) or _literal_address(host) is not None:
                raise ValueError
            hosts.add(host)
    except (TypeError, UnicodeError, ValueError):
        raise _invalid_fake_ip_configuration() from None
    if not networks or not hosts:
        raise _invalid_fake_ip_configuration()
    return FakeIpAllowance(tuple(networks), frozenset(hosts))


def _approval_file_allowance(path: Path, *, now: datetime | None) -> FakeIpAllowance:
    current_time = datetime.now(UTC) if now is None else now
    try:
        if not isinstance(current_time, datetime) or not _is_timezone_aware(current_time):
            raise ValueError
        with path.open("rb") as approval_file:
            payload_bytes = approval_file.read(_MAX_FAKE_IP_APPROVAL_FILE_BYTES + 1)
        if len(payload_bytes) > _MAX_FAKE_IP_APPROVAL_FILE_BYTES:
            raise ValueError
        payload = json.loads(
            payload_bytes.decode("utf-8"),
            object_pairs_hook=_json_object_without_duplicate_keys,
        )
        if not isinstance(payload, dict) or set(payload) != {"version", "networks", "approvals"}:
            raise ValueError
        if type(payload["version"]) is not int or payload["version"] != 1:
            raise ValueError

        networks_value = payload["networks"]
        if not isinstance(networks_value, list) or not networks_value:
            raise ValueError
        networks: list[ipaddress.IPv4Network] = []
        for raw_network in networks_value:
            if not isinstance(raw_network, str):
                raise ValueError
            network = ipaddress.ip_network(raw_network, strict=True)
            if not isinstance(network, ipaddress.IPv4Network) or not network.subnet_of(_FAKE_IP_SUPERNET):
                raise ValueError
            if network in networks:
                raise ValueError
            networks.append(network)

        approvals_value = payload["approvals"]
        if not isinstance(approvals_value, list):
            raise ValueError
        hosts: set[str] = set()
        for approval in approvals_value:
            hostname = _approval_hostname(approval)
            if hostname in hosts:
                raise ValueError
            approved_at = _approval_timestamp(approval["approved_at"])
            expires_at = _approval_timestamp(approval["expires_at"])
            if expires_at <= approved_at or expires_at <= current_time:
                raise ValueError
            hosts.add(hostname)
    except (OSError, TypeError, UnicodeError, ValueError, OverflowError, json.JSONDecodeError):
        raise _invalid_fake_ip_configuration() from None
    return FakeIpAllowance(tuple(networks), frozenset(hosts), review_unapproved_hosts=True)


def _approval_hostname(approval: object) -> str:
    required_fields = {"hostname", "approved_by", "reason", "approved_at", "expires_at"}
    if not isinstance(approval, dict) or set(approval) != required_fields:
        raise ValueError
    hostname_value = approval["hostname"]
    if not isinstance(hostname_value, str):
        raise ValueError
    hostname = hostname_value.encode("idna").decode("ascii").lower().rstrip(".")
    if (
        not hostname
        or not _valid_hostname(hostname)
        or _literal_address(hostname) is not None
    ):
        raise ValueError
    for field_name in ("approved_by", "reason"):
        value = approval[field_name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError
    return hostname


def _json_object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError
        payload[key] = value
    return payload


def _approval_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError
    timestamp = datetime.fromisoformat(value)
    if not _is_timezone_aware(timestamp):
        raise ValueError
    return timestamp


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _invalid_fake_ip_configuration() -> InvalidFakeIpConfiguration:
    return InvalidFakeIpConfiguration(_INVALID_FAKE_IP_CONFIGURATION_MESSAGE)


def _config_items(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(","))
    if not items or any(not item for item in items):
        raise ValueError
    return items


def _resolver_worker() -> None:
    while True:
        future, resolver, hostname, port = _RESOLVER_QUEUE.get()
        if future.set_running_or_notify_cancel():
            try:
                future.set_result(_collect_resolver_answers(resolver, hostname, port))
            except BaseException as exc:
                future.set_exception(exc)
        _RESOLVER_QUEUE.task_done()


for _worker_index in range(_RESOLVER_WORKERS):
    threading.Thread(
        target=_resolver_worker,
        name=f"safe-http-resolver-{_worker_index}",
        daemon=True,
    ).start()


def validate_public_url(
    url: str,
    resolver: Resolver = socket.getaddrinfo,
    *,
    deadline: float | None = None,
    fake_ip_allowance: FakeIpAllowance | None = None,
) -> ValidatedTarget:
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
            answers = _resolve_answers(resolver, ascii_hostname, port, deadline)
            for answer in answers:
                addresses.add(ipaddress.ip_address(answer[4][0]))
            if deadline is not None:
                _remaining(deadline)
        except SafeHttpError:
            raise
        except (IndexError, KeyError, OSError, TypeError, ValueError):
            raise InvalidHttpTarget("target resolution failed") from None
    if not addresses:
        raise InvalidHttpTarget("target resolution failed")
    if _requires_fake_ip_approval(
        addresses,
        hostname=ascii_hostname,
        is_literal=literal_address is not None,
        fake_ip_allowance=fake_ip_allowance,
    ):
        raise FakeIpApprovalRequired(ascii_hostname)
    if any(
        not _is_allowed_address(
            address,
            hostname=ascii_hostname,
            is_literal=literal_address is not None,
            fake_ip_allowance=fake_ip_allowance,
        )
        for address in addresses
    ):
        raise BlockedNetworkTarget("network target is blocked")
    if len(addresses) > MAX_VALIDATED_ADDRESSES:
        raise InvalidHttpTarget("too many resolved addresses")

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
    fake_ip_allowance: FakeIpAllowance | None = None,
) -> SafeHttpResponse:
    if max_bytes < 0 or max_redirects < 0 or timeout_seconds <= 0:
        raise ValueError("safe_fetch limits must be positive")
    deadline = time.monotonic() + timeout_seconds
    connector = connector or connect_pinned
    base_headers = _validated_headers(headers)
    current_url = url
    redirects = 0

    while True:
        _remaining(deadline)
        target = validate_public_url(
            current_url,
            resolver=resolver,
            deadline=deadline,
            fake_ip_allowance=fake_ip_allowance,
        )
        request_headers = dict(base_headers)
        request_headers["Host"] = _host_header(target)
        response = None
        connection = None
        try:
            try:
                response, connection = connector(target, _remaining(deadline), request_headers)
            except SafeHttpError:
                raise
            except (OSError, TimeoutError, ValueError, http.client.HTTPException):
                if time.monotonic() >= deadline:
                    raise SafeHttpError("HTTP fetch timed out") from None
                raise SafeHttpError("HTTP fetch failed") from None

            _remaining(deadline)
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
                _set_connection_timeout(connection, _remaining(deadline))
                body = response.read(max_bytes + 1)
            except (OSError, TimeoutError, http.client.HTTPException):
                if time.monotonic() >= deadline:
                    raise SafeHttpError("HTTP fetch timed out") from None
                raise SafeHttpError("HTTP fetch failed") from None
            _remaining(deadline)
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
    if len(target.validated_ips) > MAX_VALIDATED_ADDRESSES:
        raise InvalidHttpTarget("too many resolved addresses")
    deadline = time.monotonic() + timeout_seconds
    last_error: BaseException | None = None
    for address in target.validated_ips:
        raw_socket = None
        connection = None
        succeeded = False
        try:
            remaining = _remaining(deadline)
            connection = http.client.HTTPConnection(target.original_hostname, target.port, timeout=remaining)
            raw_socket = socket.create_connection((address, target.port), timeout=remaining)
            _set_socket_timeout(raw_socket, _remaining(deadline))
            if target.scheme == "https":
                raw_socket = ssl.create_default_context().wrap_socket(
                    raw_socket,
                    server_hostname=target.original_hostname,
                )
                _set_socket_timeout(raw_socket, _remaining(deadline))
            connection.sock = raw_socket
            _set_socket_timeout(raw_socket, _remaining(deadline))
            connection.request("GET", target.request_path, headers=dict(headers))
            _set_socket_timeout(raw_socket, _remaining(deadline))
            response = connection.getresponse()
            _remaining(deadline)
            succeeded = True
            return response, connection
        except SafeHttpError:
            raise
        except (OSError, TimeoutError, ValueError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            if not succeeded:
                _close(connection)
                _close(raw_socket)
        if time.monotonic() >= deadline:
            raise SafeHttpError("HTTP fetch timed out") from None
    if last_error is None:
        raise OSError("no validated address available")
    raise SafeHttpError("HTTP fetch failed") from None


def _resolve_answers(resolver: Resolver, hostname: str, port: int, deadline: float | None) -> list[tuple]:
    if deadline is None:
        return _collect_resolver_answers(resolver, hostname, port)

    remaining = _remaining(deadline)
    future: Future = Future()
    try:
        _RESOLVER_QUEUE.put_nowait((future, resolver, hostname, port))
    except queue.Full:
        future.cancel()
        raise SafeHttpError("HTTP fetch timed out") from None
    try:
        remaining = min(remaining, _remaining(deadline))
        return future.result(timeout=remaining)
    except TimeoutError:
        future.cancel()
        raise SafeHttpError("HTTP fetch timed out") from None
    except BaseException:
        future.cancel()
        raise


def _collect_resolver_answers(resolver: Resolver, hostname: str, port: int) -> list[tuple]:
    answers = resolver(hostname, port, type=socket.SOCK_STREAM)
    collected = []
    try:
        for answer in answers:
            collected.append(answer)
            if len(collected) > MAX_RESOLVED_ADDRESSES:
                resolved = [ipaddress.ip_address(item[4][0]) for item in collected]
                if any(not _is_global_address(address) for address in resolved):
                    raise BlockedNetworkTarget("network target is blocked")
                raise InvalidHttpTarget("too many resolved addresses")
    finally:
        _close(answers)
    return collected


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SafeHttpError("HTTP fetch timed out") from None
    return remaining


def _set_socket_timeout(sock: object, timeout_seconds: float) -> None:
    settimeout = getattr(sock, "settimeout", None)
    if callable(settimeout):
        settimeout(timeout_seconds)


def _set_connection_timeout(connection: object | None, timeout_seconds: float) -> None:
    _set_socket_timeout(getattr(connection, "sock", None), timeout_seconds)


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


def _is_allowed_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    hostname: str,
    is_literal: bool,
    fake_ip_allowance: FakeIpAllowance | None,
) -> bool:
    if _is_global_address(address):
        return True
    if is_literal or not isinstance(address, ipaddress.IPv4Address) or fake_ip_allowance is None:
        return False
    return hostname in fake_ip_allowance.hosts and _is_permitted_fake_ip_address(
        address,
        fake_ip_allowance.networks,
    )


def _requires_fake_ip_approval(
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address],
    *,
    hostname: str,
    is_literal: bool,
    fake_ip_allowance: FakeIpAllowance | None,
) -> bool:
    if (
        is_literal
        or fake_ip_allowance is None
        or not fake_ip_allowance.review_unapproved_hosts
        or hostname in fake_ip_allowance.hosts
    ):
        return False
    return all(
        _is_permitted_fake_ip_address(address, fake_ip_allowance.networks)
        for address in addresses
    )


def _is_permitted_fake_ip_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    networks: tuple[ipaddress.IPv4Network, ...],
) -> bool:
    return isinstance(address, ipaddress.IPv4Address) and any(
        isinstance(network, ipaddress.IPv4Network)
        and network.subnet_of(_FAKE_IP_SUPERNET)
        and address in network
        for network in networks
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
