from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address
from time import perf_counter
from typing import Any

from aiohttp import ClientSession
from aiohttp_socks import ProxyConnector

from proxy_pool.config import CheckerSettings, Settings, load_config
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


PROTOCOLS: tuple[Protocol, ...] = ("http", "socks4", "socks5")


@dataclass(frozen=True, slots=True)
class PlannedAttempt:
    capability: str
    endpoint: str


@dataclass(frozen=True, slots=True)
class CheckAttempt:
    success: bool
    capability: str
    observed_ip: str | None
    country_code: str
    timeout: float | None
    error: str | None


def extract_observed_ip(data: Mapping[str, Any]) -> tuple[str, str] | None:
    value = data.get("query") or data.get("origin") or data.get("ip")
    if not isinstance(value, str):
        return None

    observed = value.split(",", 1)[0].strip()
    try:
        ip_address(observed)
    except ValueError:
        return None

    country_code = data.get("countryCode")
    return observed, country_code if isinstance(country_code, str) else ""


def endpoint_supports_capability(endpoint: str, capability: str) -> bool:
    if capability == "http":
        return endpoint.startswith("http://")
    if capability == "https":
        return endpoint.startswith("https://")
    return False


def build_attempt_plan(
    candidate: ProxyCandidate,
    checker: CheckerSettings,
) -> tuple[PlannedAttempt, ...]:
    capabilities: list[str] = []
    if checker.check_http:
        capabilities.append("http")
    if checker.check_https:
        capabilities.append("https")

    attempts: list[PlannedAttempt] = []
    for _ in range(checker.attempts_per_proxy):
        for capability in capabilities:
            for endpoint in checker.endpoints:
                if endpoint_supports_capability(endpoint, capability):
                    attempts.append(PlannedAttempt(capability=capability, endpoint=endpoint))
    return tuple(attempts)


def calculate_score(
    success_rate: float,
    supports_https: bool,
    is_anonymous: bool,
    avg_timeout: float,
) -> float:
    latency_penalty = min(20.0, max(0.0, avg_timeout * 10.0))
    score = (
        success_rate * 70.0
        + (15.0 if supports_https else 0.0)
        + (10.0 if is_anonymous else 0.0)
        - latency_penalty
    )
    return round(min(100.0, max(0.0, score)), 2)


def aggregate_attempts(
    address: str,
    candidate_ip: str,
    attempts: Iterable[CheckAttempt],
    required_successes: int,
    min_success_rate: float,
    checked_at: str,
) -> CheckedProxy | None:
    attempt_list = list(attempts)
    successes = [attempt for attempt in attempt_list if attempt.success]
    failures = [attempt for attempt in attempt_list if not attempt.success]
    success_count = len(successes)
    failure_count = len(failures)
    total_count = success_count + failure_count
    success_rate = success_count / total_count if total_count else 0.0

    if success_count < required_successes or success_rate < min_success_rate:
        return None

    successful_timeouts = [attempt.timeout for attempt in successes if attempt.timeout is not None]
    if not successful_timeouts:
        return None

    avg_timeout = round(sum(successful_timeouts) / len(successful_timeouts), 6)
    country_code = next((attempt.country_code for attempt in successes if attempt.country_code), "")
    is_anonymous = any(attempt.observed_ip != candidate_ip for attempt in successes if attempt.observed_ip)
    supports_http = any(attempt.capability == "http" for attempt in successes)
    supports_https = any(attempt.capability == "https" for attempt in successes)
    last_error = next((attempt.error for attempt in reversed(failures) if attempt.error), None)

    return CheckedProxy(
        address=address,
        country_code=country_code,
        is_anonymous=is_anonymous,
        timeout=avg_timeout,
        score=calculate_score(success_rate, supports_https, is_anonymous, avg_timeout),
        success_rate=success_rate,
        success_count=success_count,
        failure_count=failure_count,
        supports_http=supports_http,
        supports_https=supports_https,
        avg_timeout=avg_timeout,
        last_error=last_error,
        checked_at=checked_at,
    )


async def run_attempt(
    candidate: ProxyCandidate,
    protocol: Protocol,
    endpoint: str,
    capability: str,
    timeout: float,
) -> CheckAttempt:
    start = perf_counter()
    try:
        connector = ProxyConnector.from_url(f"{protocol}://{candidate.address}")
        async with ClientSession(connector=connector) as session:
            async with session.get(
                endpoint,
                timeout=timeout,
                raise_for_status=True,
            ) as response:
                data = await response.json()
        parsed = extract_observed_ip(data)
        if parsed is None:
            return CheckAttempt(False, capability, None, "", None, "missing observed ip")
        observed_ip, country_code = parsed
        return CheckAttempt(True, capability, observed_ip, country_code, perf_counter() - start, None)
    except Exception as exc:
        return CheckAttempt(False, capability, None, "", None, type(exc).__name__)


async def check_candidate(
    candidate: ProxyCandidate,
    protocol: Protocol,
    timeout: float,
    semaphore: asyncio.Semaphore,
    checker: CheckerSettings,
    checked_at: str,
) -> CheckedProxy | None:
    attempt_plan = build_attempt_plan(candidate, checker)
    async with semaphore:
        attempts = await asyncio.gather(
            *(
                run_attempt(candidate, protocol, item.endpoint, item.capability, timeout)
                for item in attempt_plan
            )
        )
    return aggregate_attempts(
        address=candidate.address,
        candidate_ip=candidate.ip,
        attempts=attempts,
        required_successes=checker.required_successes,
        min_success_rate=checker.min_success_rate,
        checked_at=checked_at,
    )


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
    checked_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    for protocol, protocol_candidates in candidates.items():
        results = await asyncio.gather(
            *(
                check_candidate(
                    candidate,
                    protocol,
                    settings.timeout,
                    semaphore,
                    settings.checker,
                    checked_at,
                )
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
