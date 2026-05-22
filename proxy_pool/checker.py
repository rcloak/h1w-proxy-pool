from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import Any
from time import perf_counter

from aiohttp import ClientSession
from aiohttp_socks import ProxyConnector

from proxy_pool.config import Settings, load_config
from proxy_pool.models import (
    CheckedProxy,
    Protocol,
    ProxyCandidate,
    ProxyJson,
    checked_proxy_to_json,
    empty_proxy_json,
)
from proxy_pool.sources import collect_candidates
from proxy_pool.storage import write_proxy_json


CHECK_URL = "http://ip-api.com/json/?fields=8219"
PROTOCOLS: tuple[Protocol, ...] = ("http", "socks4", "socks5")


async def check_candidate(
    candidate: ProxyCandidate,
    protocol: Protocol,
    timeout: float,
    semaphore: asyncio.Semaphore,
) -> CheckedProxy | None:
    async with semaphore:
        start = perf_counter()
        try:
            connector = ProxyConnector.from_url(f"{protocol}://{candidate.address}")
            async with ClientSession(connector=connector) as session:
                async with session.get(
                    CHECK_URL,
                    timeout=timeout,
                    raise_for_status=True,
                ) as response:
                    data = await response.json()
            return _checked_proxy_from_response(candidate, data, perf_counter() - start)
        except Exception:
            return None


def _checked_proxy_from_response(
    candidate: ProxyCandidate,
    data: Mapping[str, Any],
    elapsed: float,
) -> CheckedProxy | None:
    query = data.get("query")
    country_code = data.get("countryCode")
    if not isinstance(query, str) or not query:
        return None
    if not isinstance(country_code, str) or not country_code:
        return None

    return CheckedProxy(
        address=candidate.address,
        country_code=country_code,
        is_anonymous=candidate.ip != query,
        timeout=elapsed,
    )


def sort_checked(proxies: Iterable[CheckedProxy], sort_by_speed: bool) -> list[CheckedProxy]:
    if sort_by_speed:
        return sorted(proxies, key=lambda proxy: proxy.timeout)
    return sorted(
        proxies,
        key=lambda proxy: tuple(map(int, proxy.address.replace(":", ".").split("."))),
    )


def build_proxy_json(proxies: Mapping[Protocol, Iterable[CheckedProxy]]) -> ProxyJson:
    payload = empty_proxy_json()
    for protocol in PROTOCOLS:
        payload[protocol] = [
            checked_proxy_to_json(proxy)
            for proxy in proxies.get(protocol, ())
        ]
    payload["total_count_of_proxies"] = sum(
        len(payload[protocol]) for protocol in PROTOCOLS
    )
    return payload


async def run_pipeline(settings: Settings) -> ProxyJson:
    candidates = await collect_candidates(settings.sources)
    semaphore = asyncio.Semaphore(settings.max_connections)
    checked: dict[Protocol, list[CheckedProxy]] = {protocol: [] for protocol in PROTOCOLS}

    for protocol, protocol_candidates in candidates.items():
        results = await asyncio.gather(
            *(
                check_candidate(candidate, protocol, settings.timeout, semaphore)
                for candidate in protocol_candidates
            )
        )
        checked[protocol].extend(result for result in results if result is not None)

    sorted_proxies = {
        protocol: sort_checked(proxies, settings.sort_by_speed)
        for protocol, proxies in checked.items()
    }
    payload = build_proxy_json(sorted_proxies)
    write_proxy_json(settings.result_path, payload)
    return payload


async def async_main() -> None:
    await run_pipeline(load_config())


def main() -> None:
    asyncio.run(async_main())
