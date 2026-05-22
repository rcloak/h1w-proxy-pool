from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, NotRequired, TypedDict


Protocol = Literal["http", "socks4", "socks5"]
Capability = Literal["http", "https"]


@dataclass(frozen=True, slots=True)
class ProxyCandidate:
    address: str
    ip: str


@dataclass(init=False, slots=True)
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

    def __init__(
        self,
        endpoint: str | None = None,
        source_protocol: Protocol = "http",
        usable_as: tuple[Capability, ...] | None = None,
        exit_ip: str = "",
        country_code: str = "",
        anonymous: bool | None = None,
        score: float = 0.0,
        success_rate: float = 0.0,
        checks_passed: int | None = None,
        checks_failed: int | None = None,
        avg_latency_ms: int | None = None,
        last_error: str | None = None,
        checked_at: str = "",
        *,
        address: str | None = None,
        is_anonymous: bool | None = None,
        timeout: float | None = None,
        success_count: int | None = None,
        failure_count: int | None = None,
        supports_http: bool = False,
        supports_https: bool = False,
        avg_timeout: float | None = None,
    ) -> None:
        resolved_endpoint = endpoint if endpoint is not None else address
        if resolved_endpoint is None:
            raise TypeError("CheckedProxy requires endpoint")

        if usable_as is None:
            capabilities: list[Capability] = []
            if supports_http:
                capabilities.append("http")
            if supports_https:
                capabilities.append("https")
            usable_as = tuple(capabilities)

        latency_seconds = avg_timeout if avg_timeout is not None else timeout
        if avg_latency_ms is None:
            avg_latency_ms = int(round((latency_seconds or 0.0) * 1000))

        self.endpoint = resolved_endpoint
        self.source_protocol = source_protocol
        self.usable_as = usable_as
        self.exit_ip = exit_ip
        self.country_code = country_code
        self.anonymous = bool(anonymous if anonymous is not None else is_anonymous)
        self.score = score
        self.success_rate = success_rate
        self.checks_passed = checks_passed if checks_passed is not None else (success_count or 0)
        self.checks_failed = checks_failed if checks_failed is not None else (failure_count or 0)
        self.avg_latency_ms = avg_latency_ms
        self.last_error = last_error
        self.checked_at = checked_at

    @property
    def address(self) -> str:
        return self.endpoint

    @property
    def is_anonymous(self) -> bool:
        return self.anonymous

    @property
    def timeout(self) -> float:
        return self.avg_latency_ms / 1000

    @property
    def success_count(self) -> int:
        return self.checks_passed

    @property
    def failure_count(self) -> int:
        return self.checks_failed

    @property
    def supports_http(self) -> bool:
        return "http" in self.usable_as

    @property
    def supports_https(self) -> bool:
        return "https" in self.usable_as

    @property
    def avg_timeout(self) -> float:
        return self.avg_latency_ms / 1000


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


class ProxyJsonItem(TypedDict):
    address: str
    countryCode: str
    is_anonymous: bool
    timeout: float
    score: NotRequired[float]
    success_rate: NotRequired[float]
    success_count: NotRequired[int]
    failure_count: NotRequired[int]
    supports_http: NotRequired[bool]
    supports_https: NotRequired[bool]
    avg_timeout: NotRequired[float]
    last_error: NotRequired[str | None]
    checked_at: NotRequired[str]


class ProxyJson(TypedDict):
    total_count_of_proxies: int
    http: list[ProxyJsonItem]
    socks4: list[ProxyJsonItem]
    socks5: list[ProxyJsonItem]


def empty_proxy_document(generated_at: str = "") -> ProxyDocument:
    return {
        "version": 2,
        "generated_at": generated_at,
        "total": 0,
        "items": [],
    }


def checked_proxy_to_item(proxy: CheckedProxy) -> ProxyItem:
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


def empty_proxy_json() -> ProxyJson:
    return {
        "total_count_of_proxies": 0,
        "http": [],
        "socks4": [],
        "socks5": [],
    }


def checked_proxy_to_json(proxy: CheckedProxy) -> ProxyJsonItem:
    timeout = proxy.timeout
    return {
        "address": proxy.address,
        "countryCode": proxy.country_code,
        "is_anonymous": proxy.is_anonymous,
        "timeout": timeout,
        "score": _clamp_float(proxy.score, 0.0, 100.0, 0.0),
        "success_rate": _clamp_float(proxy.success_rate, 0.0, 1.0, 0.0),
        "success_count": _nonnegative_int(proxy.success_count),
        "failure_count": _nonnegative_int(proxy.failure_count),
        "supports_http": proxy.supports_http,
        "supports_https": proxy.supports_https,
        "avg_timeout": proxy.avg_timeout or timeout,
        "last_error": proxy.last_error,
        "checked_at": proxy.checked_at,
    }


def _clamp_float(value: float, minimum: float, maximum: float, default: float) -> float:
    if not isfinite(value):
        return default
    return min(maximum, max(minimum, value))


def _nonnegative_int(value: int) -> int:
    return max(0, int(value))
