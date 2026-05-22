from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from math import isfinite
from typing import Literal, TypedDict


Protocol = Literal["http", "socks4", "socks5"]
Capability = Literal["http", "https"]


@dataclass(frozen=True, slots=True)
class ProxyCandidate:
    address: str
    ip: str


@dataclass(slots=True)
class CheckedProxy:
    endpoint: str
    source_protocol: Protocol
    usable_as: tuple[Capability, ...]
    exit_ip: str
    country_code: str
    anonymous: bool
    score: float
    success_rate: float
    checks_passed: int
    checks_failed: int
    avg_latency_ms: int
    last_error: str | None
    checked_at: str


class ProxyQuality(TypedDict):
    score: float
    success_rate: float
    checks_passed: int
    checks_failed: int
    avg_latency_ms: int
    last_error: str | None


class ProxyNetwork(TypedDict):
    exit_ip: str
    country_code: str
    anonymous: bool


class ProxyTimestamps(TypedDict):
    checked_at: str


class ProxyItem(TypedDict):
    endpoint: str
    source_protocol: Protocol
    usable_as: list[Capability]
    quality: ProxyQuality
    network: ProxyNetwork
    timestamps: ProxyTimestamps


class ProxyDocument(TypedDict):
    version: int
    generated_at: str
    total: int
    items: list[ProxyItem]


def empty_proxy_document(generated_at: str = "") -> ProxyDocument:
    return {
        "version": 2,
        "generated_at": generated_at,
        "total": 0,
        "items": [],
    }


def checked_proxy_to_item(proxy: CheckedProxy) -> ProxyItem:
    if not valid_endpoint(proxy.endpoint):
        raise ValueError("CheckedProxy endpoint is required for v2 item")
    if proxy.source_protocol not in ("http", "socks4", "socks5"):
        raise ValueError("CheckedProxy source_protocol is invalid for v2 item")
    if not proxy.usable_as or any(capability not in ("http", "https") for capability in proxy.usable_as):
        raise ValueError("CheckedProxy usable_as is required for v2 item")
    try:
        ip_address(proxy.exit_ip)
    except ValueError as exc:
        raise ValueError("CheckedProxy exit_ip must be a valid IP address") from exc

    return {
        "endpoint": proxy.endpoint,
        "source_protocol": proxy.source_protocol,
        "usable_as": list(proxy.usable_as),
        "quality": {
            "score": _clamp_float(proxy.score, 0.0, 100.0, 0.0),
            "success_rate": _clamp_float(proxy.success_rate, 0.0, 1.0, 0.0),
            "checks_passed": _nonnegative_int(proxy.checks_passed),
            "checks_failed": _nonnegative_int(proxy.checks_failed),
            "avg_latency_ms": _nonnegative_int(proxy.avg_latency_ms),
            "last_error": proxy.last_error,
        },
        "network": {
            "exit_ip": proxy.exit_ip,
            "country_code": proxy.country_code,
            "anonymous": proxy.anonymous,
        },
        "timestamps": {"checked_at": proxy.checked_at},
    }


def valid_endpoint(value: str) -> bool:
    host, separator, port = value.rpartition(":")
    if not separator or not host or not port:
        return False
    try:
        ip_address(host)
        if not port.isdigit():
            return False
        port_number = int(port)
    except ValueError:
        return False
    return 1 <= port_number <= 65535


def _clamp_float(value: float, minimum: float, maximum: float, default: float) -> float:
    if not isfinite(value):
        return default
    return min(maximum, max(minimum, value))


def _nonnegative_int(value: int) -> int:
    return max(0, int(value))
