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


class ProxyJsonItem(TypedDict):
    address: str
    countryCode: str
    is_anonymous: bool
    timeout: float


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
    }
