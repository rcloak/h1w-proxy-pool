from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


Protocol = Literal["http", "socks4", "socks5"]


@dataclass(frozen=True, slots=True)
class ProxyCandidate:
    address: str
    ip: str


@dataclass(slots=True)
class CheckedProxy:
    address: str
    country_code: str
    is_anonymous: bool
    timeout: float
    score: float = 0.0
    success_rate: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    supports_http: bool = False
    supports_https: bool = False
    avg_timeout: float = 0.0
    last_error: str | None = None
    checked_at: str = ""


class ProxyJsonItem(TypedDict):
    address: str
    countryCode: str
    is_anonymous: bool
    timeout: float
    score: float
    success_rate: float
    success_count: int
    failure_count: int
    supports_http: bool
    supports_https: bool
    avg_timeout: float
    last_error: str | None
    checked_at: str


class ProxyJson(TypedDict):
    total_count_of_proxies: int
    http: list[ProxyJsonItem]
    socks4: list[ProxyJsonItem]
    socks5: list[ProxyJsonItem]


def empty_proxy_json() -> ProxyJson:
    return {
        "total_count_of_proxies": 0,
        "http": [],
        "socks4": [],
        "socks5": [],
    }


def checked_proxy_to_json(proxy: CheckedProxy) -> ProxyJsonItem:
    return {
        "address": proxy.address,
        "countryCode": proxy.country_code,
        "is_anonymous": proxy.is_anonymous,
        "timeout": proxy.timeout,
        "score": proxy.score,
        "success_rate": proxy.success_rate,
        "success_count": proxy.success_count,
        "failure_count": proxy.failure_count,
        "supports_http": proxy.supports_http,
        "supports_https": proxy.supports_https,
        "avg_timeout": proxy.avg_timeout,
        "last_error": proxy.last_error,
        "checked_at": proxy.checked_at,
    }
