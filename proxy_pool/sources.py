from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping

from aiohttp import ClientSession

from proxy_pool.models import Protocol, ProxyCandidate


PROXY_PATTERN = re.compile(
    r"(?<![\d.])(("
    + r"(?:[1-9]|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])"
    + r"\."
    + r"(?:\d|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])"
    + r"\."
    + r"(?:\d|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])"
    + r"\."
    + r"(?:\d|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])"
    + r"):"
    + r"(?:\d|[1-9]\d{1,3}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5])"
    + r")(?!\d)"
)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:107.0) Gecko/20100101 Firefox/107.0"


def extract_proxy_candidates(text: str) -> tuple[ProxyCandidate, ...]:
    candidates: list[ProxyCandidate] = []
    seen: set[str] = set()

    for match in PROXY_PATTERN.finditer(text):
        address = match.group(1)
        if address in seen:
            continue
        seen.add(address)
        candidates.append(ProxyCandidate(address=address, ip=match.group(2)))

    return tuple(candidates)


async def fetch_source(session: ClientSession, url: str, timeout: float = 15) -> str:
    async with session.get(url, timeout=timeout, raise_for_status=True) as response:
        return await response.text()


async def collect_candidates(
    sources: Mapping[Protocol, tuple[str, ...]],
) -> dict[Protocol, set[ProxyCandidate]]:
    results: dict[Protocol, set[ProxyCandidate]] = {protocol: set() for protocol in sources}

    async with ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        async def fetch_one(protocol: Protocol, url: str) -> None:
            try:
                text = await fetch_source(session, url)
            except Exception:
                return
            results[protocol].update(extract_proxy_candidates(text))

        await asyncio.gather(
            *(fetch_one(protocol, url) for protocol, urls in sources.items() for url in urls)
        )

    return results
