from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping, Sequence
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
    ProxyDocument,
    RefreshProgress,
    checked_proxy_to_item,
)
from proxy_pool.sources import collect_candidates
from proxy_pool.storage import write_proxy_document

DEFAULT_BATCH_SIZE = 500
ProgressCallback = Callable[[RefreshProgress], None]


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
    source_protocol: Protocol,
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
    avg_latency_ms = int(round(avg_timeout * 1000))
    country_code = next((attempt.country_code for attempt in successes if attempt.country_code), "")
    exit_ip = next((attempt.observed_ip for attempt in successes if attempt.observed_ip), "")
    is_anonymous = any(attempt.observed_ip != candidate_ip for attempt in successes if attempt.observed_ip)
    supports_http = any(attempt.capability == "http" for attempt in successes)
    supports_https = any(attempt.capability == "https" for attempt in successes)
    usable_as = tuple(
        capability
        for capability, supported in (("http", supports_http), ("https", supports_https))
        if supported
    )
    last_error = next((attempt.error for attempt in reversed(failures) if attempt.error), None)

    return CheckedProxy(
        endpoint=address,
        source_protocol=source_protocol,
        usable_as=usable_as,
        exit_ip=exit_ip,
        country_code=country_code,
        anonymous=is_anonymous,
        score=calculate_score(success_rate, supports_https, is_anonymous, avg_timeout),
        success_rate=success_rate,
        checks_passed=success_count,
        checks_failed=failure_count,
        avg_latency_ms=avg_latency_ms,
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


async def run_attempt_with_semaphore(
    candidate: ProxyCandidate,
    protocol: Protocol,
    endpoint: str,
    capability: str,
    timeout: float,
    semaphore: asyncio.Semaphore,
) -> CheckAttempt:
    async with semaphore:
        return await run_attempt(candidate, protocol, endpoint, capability, timeout)


async def check_candidate(
    candidate: ProxyCandidate,
    protocol: Protocol,
    timeout: float,
    semaphore: asyncio.Semaphore,
    checker: CheckerSettings,
    checked_at: str,
) -> CheckedProxy | None:
    attempt_plan = build_attempt_plan(candidate, checker)
    if not attempt_plan:
        attempts = (
            CheckAttempt(False, "none", None, "", None, "no matching check endpoints"),
        )
    else:
        attempts = await asyncio.gather(
            *(
                run_attempt_with_semaphore(
                    candidate,
                    protocol,
                    item.endpoint,
                    item.capability,
                    timeout,
                    semaphore,
                )
                for item in attempt_plan
            )
        )
    return aggregate_attempts(
        address=candidate.address,
        source_protocol=protocol,
        candidate_ip=candidate.ip,
        attempts=attempts,
        required_successes=checker.required_successes,
        min_success_rate=checker.min_success_rate,
        checked_at=checked_at,
    )


def sort_checked(proxies: Iterable[CheckedProxy], sort_by_speed: bool) -> list[CheckedProxy]:
    if sort_by_speed:
        return sorted(
            proxies,
            key=lambda proxy: (-proxy.score, proxy.avg_latency_ms, _natural_address_key(proxy.endpoint)),
        )
    return sorted(
        proxies,
        key=lambda proxy: _natural_address_key(proxy.endpoint),
    )


def _natural_address_key(address: str) -> tuple[int, ...]:
    return tuple(map(int, address.replace(":", ".").split(".")))


def build_proxy_document(proxies: Iterable[CheckedProxy], generated_at: str) -> ProxyDocument:
    items = [checked_proxy_to_item(proxy) for proxy in proxies]
    return {"version": 2, "generated_at": generated_at, "total": len(items), "items": items}


def _candidate_batches(candidates: Sequence[ProxyCandidate], batch_size: int) -> Iterable[Sequence[ProxyCandidate]]:
    for index in range(0, len(candidates), batch_size):
        yield candidates[index : index + batch_size]


async def run_pipeline(
    settings: Settings,
    on_progress: ProgressCallback | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ProxyDocument:
    candidates = await collect_candidates(settings.sources)
    semaphore = asyncio.Semaphore(settings.max_connections)
    checked: list[CheckedProxy] = []
    checked_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    started_at = datetime.now(UTC).isoformat()
    total_candidates = sum(len(protocol_candidates) for protocol_candidates in candidates.values())
    checked_count = 0
    effective_batch_size = max(1, batch_size)
    payload: ProxyDocument | None = None

    def emit_progress(current_protocol: Protocol | None) -> None:
        if on_progress is None:
            return
        on_progress(
            {
                "status": "running",
                "started_at": started_at,
                "finished_at": None,
                "checked": checked_count,
                "total": total_candidates,
                "alive": len(checked),
                "current_protocol": current_protocol,
            }
        )

    emit_progress(None)

    for protocol, protocol_candidates in candidates.items():
        ordered_candidates = sorted(
            protocol_candidates,
            key=lambda candidate: _natural_address_key(candidate.address),
        )
        for batch in _candidate_batches(ordered_candidates, effective_batch_size):
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
                    for candidate in batch
                )
            )
            checked.extend(result for result in results if result is not None)
            checked_count += len(batch)
            sorted_proxies = sort_checked(checked, settings.sort_by_speed)
            payload = build_proxy_document(sorted_proxies, generated_at=checked_at)
            write_proxy_document(settings.result_path, payload)
            emit_progress(protocol)

    if payload is None:
        payload = build_proxy_document([], generated_at=checked_at)
        write_proxy_document(settings.result_path, payload)
    return payload


async def async_main() -> None:
    await run_pipeline(load_config())


def main() -> None:
    asyncio.run(async_main())
