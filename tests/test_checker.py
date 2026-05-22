import asyncio
from pathlib import Path

from proxy_pool.checker import (
    CheckAttempt,
    aggregate_attempts,
    build_attempt_plan,
    build_proxy_document,
    calculate_score,
    check_candidate,
    endpoint_supports_capability,
    extract_observed_ip,
    run_pipeline,
    sort_checked,
)
from proxy_pool.config import DEFAULT_CHECK_ENDPOINTS, CheckerSettings, DeadCacheSettings, Settings
from proxy_pool.models import CheckedProxy, ProxyCandidate
from proxy_pool.storage import read_proxy_document


def make_checked_proxy(
    endpoint: str,
    *,
    score: float = 0.0,
    avg_latency_ms: int = 0,
    country_code: str = "US",
    anonymous: bool = True,
) -> CheckedProxy:
    return CheckedProxy(
        endpoint=endpoint,
        source_protocol="http",
        usable_as=("http",),
        exit_ip="8.8.8.8",
        country_code=country_code,
        anonymous=anonymous,
        score=score,
        success_rate=1.0,
        checks_passed=1,
        checks_failed=0,
        avg_latency_ms=avg_latency_ms,
        last_error=None,
        checked_at="2026-05-22T12:00:00Z",
    )


def test_sort_checked_sorts_by_timeout():
    slow = make_checked_proxy("1.2.3.4:80", country_code="US", anonymous=True, avg_latency_ms=1100)
    fast = make_checked_proxy("5.6.7.8:1080", country_code="DE", anonymous=False, avg_latency_ms=200)

    result = sort_checked([slow, fast], sort_by_speed=True)

    assert result == [fast, slow]


def test_sort_checked_prefers_score_then_timeout_then_address():
    proxies = [
        make_checked_proxy("2.2.2.2:80", country_code="US", anonymous=True, score=90.0, avg_latency_ms=100),
        make_checked_proxy("1.1.1.1:80", country_code="US", anonymous=True, score=95.0, avg_latency_ms=200),
        make_checked_proxy("3.3.3.3:80", country_code="US", anonymous=True, score=90.0, avg_latency_ms=300),
    ]

    assert [proxy.endpoint for proxy in sort_checked(proxies, sort_by_speed=True)] == [
        "1.1.1.1:80",
        "2.2.2.2:80",
        "3.3.3.3:80",
    ]


def test_sort_checked_sorts_by_natural_address():
    high_port = make_checked_proxy("1.2.3.4:100", country_code="US", anonymous=True, avg_latency_ms=100)
    later_ip = make_checked_proxy("1.2.3.10:80", country_code="US", anonymous=True, avg_latency_ms=100)
    low_port = make_checked_proxy("1.2.3.4:80", country_code="US", anonymous=True, avg_latency_ms=100)

    result = sort_checked([high_port, later_ip, low_port], sort_by_speed=False)

    assert result == [low_port, high_port, later_ip]


def test_build_proxy_document_returns_v2_shape():
    result = build_proxy_document(
        [
            CheckedProxy(
                endpoint="1.2.3.4:80",
                source_protocol="http",
                usable_as=("http",),
                exit_ip="8.8.8.8",
                country_code="US",
                anonymous=True,
                score=50.0,
                success_rate=1.0,
                checks_passed=1,
                checks_failed=0,
                avg_latency_ms=500,
                last_error=None,
                checked_at="2026-05-22T12:00:00Z",
            )
        ],
        generated_at="2026-05-22T12:00:00Z",
    )

    assert result["version"] == 2
    assert result["generated_at"] == "2026-05-22T12:00:00Z"
    assert result["total"] == 1
    assert result["items"][0]["source_protocol"] == "http"


def test_extract_observed_ip_supports_common_response_shapes():
    assert extract_observed_ip({"query": "1.2.3.4", "countryCode": "US"}) == ("1.2.3.4", "US")
    assert extract_observed_ip({"origin": "5.6.7.8, 10.0.0.1"}) == ("5.6.7.8", "")
    assert extract_observed_ip({"ip": "9.9.9.9"}) == ("9.9.9.9", "")


def test_extract_observed_ip_rejects_missing_or_invalid_ip():
    assert extract_observed_ip({}) is None
    assert extract_observed_ip({"origin": "not-an-ip"}) is None
    assert extract_observed_ip({"ip": ""}) is None


def test_calculate_score_clamps_to_zero_to_one_hundred():
    assert calculate_score(success_rate=1.0, supports_https=True, is_anonymous=True, avg_timeout=0.1) == 94.0
    assert calculate_score(success_rate=0.0, supports_https=False, is_anonymous=False, avg_timeout=99.0) == 0.0


def test_aggregate_attempts_builds_quality_proxy():
    attempts = [
        CheckAttempt(success=True, capability="http", observed_ip="8.8.8.8", country_code="US", timeout=0.2, error=None),
        CheckAttempt(success=True, capability="https", observed_ip="8.8.8.8", country_code="US", timeout=0.4, error=None),
        CheckAttempt(success=False, capability="https", observed_ip=None, country_code="", timeout=None, error="timeout"),
    ]

    proxy = aggregate_attempts(
        address="1.2.3.4:80",
        source_protocol="http",
        candidate_ip="1.2.3.4",
        attempts=attempts,
        required_successes=1,
        min_success_rate=0.5,
        checked_at="2026-05-22T12:00:00Z",
    )

    assert proxy is not None
    assert proxy.endpoint == "1.2.3.4:80"
    assert proxy.source_protocol == "http"
    assert proxy.usable_as == ("http", "https")
    assert proxy.exit_ip == "8.8.8.8"
    assert proxy.country_code == "US"
    assert proxy.anonymous is True
    assert proxy.checks_passed == 2
    assert proxy.checks_failed == 1
    assert proxy.success_rate == 2 / 3
    assert proxy.avg_latency_ms == 300
    assert proxy.last_error == "timeout"


def test_endpoint_supports_capability_matches_scheme():
    assert endpoint_supports_capability("http://example.test/ip", "http") is True
    assert endpoint_supports_capability("http://example.test/ip", "https") is False
    assert endpoint_supports_capability("https://example.test/ip", "https") is True


def test_build_attempt_plan_repeats_enabled_capabilities_and_matching_endpoints():
    checker = CheckerSettings(
        endpoints=("http://example.test/ip", "https://example.test/ip"),
        attempts_per_proxy=2,
        required_successes=1,
        check_http=True,
        check_https=True,
        min_success_rate=0.5,
    )

    plan = build_attempt_plan(ProxyCandidate(address="1.2.3.4:80", ip="1.2.3.4"), checker)

    assert [(item.capability, item.endpoint) for item in plan] == [
        ("http", "http://example.test/ip"),
        ("https", "https://example.test/ip"),
        ("http", "http://example.test/ip"),
        ("https", "https://example.test/ip"),
    ]


async def test_check_candidate_records_failed_attempt_when_no_endpoints_match(monkeypatch):
    captured_attempts = None

    def fake_aggregate_attempts(**kwargs):
        nonlocal captured_attempts
        captured_attempts = tuple(kwargs["attempts"])
        return None

    monkeypatch.setattr("proxy_pool.checker.aggregate_attempts", fake_aggregate_attempts)
    checker = CheckerSettings(
        endpoints=("https://example.test/ip",),
        attempts_per_proxy=1,
        required_successes=1,
        check_http=True,
        check_https=False,
        min_success_rate=0.5,
    )

    result = await check_candidate(
        ProxyCandidate(address="1.2.3.4:80", ip="1.2.3.4"),
        "http",
        1.0,
        asyncio.Semaphore(1),
        checker,
        "2026-05-22T12:00:00Z",
    )

    assert result is None
    assert captured_attempts == (
        CheckAttempt(False, "none", None, "", None, "no matching check endpoints"),
    )


async def test_check_candidate_limits_concurrent_attempts_to_semaphore(monkeypatch):
    active_attempts = 0
    max_active_attempts = 0

    async def fake_run_attempt(candidate, protocol, endpoint, capability, timeout):
        nonlocal active_attempts, max_active_attempts
        active_attempts += 1
        max_active_attempts = max(max_active_attempts, active_attempts)
        await asyncio.sleep(0)
        active_attempts -= 1
        return CheckAttempt(True, capability, "8.8.8.8", "US", 0.1, None)

    monkeypatch.setattr("proxy_pool.checker.run_attempt", fake_run_attempt)
    checker = CheckerSettings(
        endpoints=(
            "http://one.example.test/ip",
            "http://two.example.test/ip",
            "http://three.example.test/ip",
            "http://four.example.test/ip",
        ),
        attempts_per_proxy=1,
        required_successes=1,
        check_http=True,
        check_https=False,
        min_success_rate=0.5,
    )

    result = await check_candidate(
        ProxyCandidate(address="1.2.3.4:80", ip="1.2.3.4"),
        "http",
        1.0,
        asyncio.Semaphore(2),
        checker,
        "2026-05-22T12:00:00Z",
    )

    assert result is not None
    assert max_active_attempts == 2


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        config_path=tmp_path / "config.ini",
        timeout=1,
        max_connections=2,
        sort_by_speed=True,
        save_path=tmp_path,
        json_result_filename="proxies.json",
        save_format="json",
        refresh_interval_seconds=60,
        sources={"http": ("https://example.test/http.txt",)},
        checker=CheckerSettings(
            endpoints=DEFAULT_CHECK_ENDPOINTS,
            attempts_per_proxy=1,
            required_successes=1,
            check_http=True,
            check_https=False,
            min_success_rate=0.5,
        ),
    )


def make_dead_cache_settings(tmp_path: Path) -> Settings:
    settings = make_settings(tmp_path)
    return Settings(
        config_path=settings.config_path,
        timeout=settings.timeout,
        max_connections=settings.max_connections,
        sort_by_speed=settings.sort_by_speed,
        save_path=settings.save_path,
        json_result_filename=settings.json_result_filename,
        save_format=settings.save_format,
        refresh_interval_seconds=settings.refresh_interval_seconds,
        sources=settings.sources,
        checker=settings.checker,
        dead_cache=DeadCacheSettings(enabled=True, database_path=tmp_path / "proxy_state.sqlite3"),
    )


async def test_run_pipeline_writes_partial_documents_after_each_batch(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path)
    candidates = {
        "http": {
            ProxyCandidate(address="3.3.3.3:80", ip="3.3.3.3"),
            ProxyCandidate(address="1.1.1.1:80", ip="1.1.1.1"),
            ProxyCandidate(address="2.2.2.2:80", ip="2.2.2.2"),
        }
    }
    writes: list[int] = []

    async def fake_collect_candidates(sources):
        return candidates

    async def fake_check_candidate(candidate, protocol, timeout, semaphore, checker, checked_at):
        if candidate.address == "2.2.2.2:80":
            return None
        return CheckedProxy(
            endpoint=candidate.address,
            source_protocol=protocol,
            usable_as=("http",),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=90.0,
            success_rate=1.0,
            checks_passed=1,
            checks_failed=0,
            avg_latency_ms=100,
            last_error=None,
            checked_at=checked_at,
        )

    def fake_write_proxy_document(path, payload):
        writes.append(payload["total"])
        from proxy_pool.storage import write_proxy_document as real_write_proxy_document

        real_write_proxy_document(path, payload)

    monkeypatch.setattr("proxy_pool.checker.collect_candidates", fake_collect_candidates)
    monkeypatch.setattr("proxy_pool.checker.check_candidate", fake_check_candidate)
    monkeypatch.setattr("proxy_pool.checker.write_proxy_document", fake_write_proxy_document)

    payload = await run_pipeline(settings, batch_size=2)

    assert writes == [1, 2]
    assert payload["total"] == 2
    assert read_proxy_document(settings.result_path)["total"] == 2


async def test_run_pipeline_reports_progress_for_batches(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path)
    candidates = {
        "http": {
            ProxyCandidate(address="3.3.3.3:80", ip="3.3.3.3"),
            ProxyCandidate(address="1.1.1.1:80", ip="1.1.1.1"),
            ProxyCandidate(address="2.2.2.2:80", ip="2.2.2.2"),
        }
    }
    progress_updates = []

    async def fake_collect_candidates(sources):
        return candidates

    async def fake_check_candidate(candidate, protocol, timeout, semaphore, checker, checked_at):
        return CheckedProxy(
            endpoint=candidate.address,
            source_protocol=protocol,
            usable_as=("http",),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=90.0,
            success_rate=1.0,
            checks_passed=1,
            checks_failed=0,
            avg_latency_ms=100,
            last_error=None,
            checked_at=checked_at,
        )

    monkeypatch.setattr("proxy_pool.checker.collect_candidates", fake_collect_candidates)
    monkeypatch.setattr("proxy_pool.checker.check_candidate", fake_check_candidate)

    await run_pipeline(settings, progress_updates.append, batch_size=2)

    assert progress_updates[0]["status"] == "running"
    assert progress_updates[0]["checked"] == 0
    assert progress_updates[0]["total"] == 3
    assert [update["checked"] for update in progress_updates[1:]] == [2, 3]
    assert progress_updates[-1]["alive"] == 3
    assert progress_updates[-1]["current_protocol"] == "http"


async def test_run_pipeline_skips_dead_cached_candidates(monkeypatch, tmp_path: Path):
    settings = make_dead_cache_settings(tmp_path)
    from proxy_pool.dead_cache import DeadProxyCache

    cache = DeadProxyCache(settings.dead_cache.database_path)
    cache.record_failure("http", "1.1.1.1:80", "TimeoutError", "2026-05-22T23:00:00+00:00")
    candidates = {
        "http": {
            ProxyCandidate(address="1.1.1.1:80", ip="1.1.1.1"),
            ProxyCandidate(address="2.2.2.2:80", ip="2.2.2.2"),
        }
    }
    checked_addresses: list[str] = []

    async def fake_collect_candidates(sources):
        return candidates

    async def fake_check_candidate(candidate, protocol, timeout, semaphore, checker, checked_at):
        checked_addresses.append(candidate.address)
        return CheckedProxy(
            endpoint=candidate.address,
            source_protocol=protocol,
            usable_as=("http",),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=90.0,
            success_rate=1.0,
            checks_passed=1,
            checks_failed=0,
            avg_latency_ms=100,
            last_error=None,
            checked_at=checked_at,
        )

    monkeypatch.setattr("proxy_pool.checker.collect_candidates", fake_collect_candidates)
    monkeypatch.setattr("proxy_pool.checker.check_candidate", fake_check_candidate)

    await run_pipeline(settings, batch_size=2)

    assert checked_addresses == ["2.2.2.2:80"]


async def test_run_pipeline_records_dead_cache_failures_and_clears_successes(monkeypatch, tmp_path: Path):
    settings = make_dead_cache_settings(tmp_path)
    from proxy_pool.dead_cache import DeadProxyCache

    cache = DeadProxyCache(settings.dead_cache.database_path)
    cache.record_failure("http", "1.1.1.1:80", "TimeoutError", "2026-05-22T10:00:00+00:00")
    candidates = {
        "http": {
            ProxyCandidate(address="1.1.1.1:80", ip="1.1.1.1"),
            ProxyCandidate(address="2.2.2.2:80", ip="2.2.2.2"),
        }
    }

    async def fake_collect_candidates(sources):
        return candidates

    async def fake_check_candidate(candidate, protocol, timeout, semaphore, checker, checked_at):
        if candidate.address == "2.2.2.2:80":
            return None
        return CheckedProxy(
            endpoint=candidate.address,
            source_protocol=protocol,
            usable_as=("http",),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=90.0,
            success_rate=1.0,
            checks_passed=1,
            checks_failed=0,
            avg_latency_ms=100,
            last_error=None,
            checked_at=checked_at,
        )

    monkeypatch.setattr("proxy_pool.checker.collect_candidates", fake_collect_candidates)
    monkeypatch.setattr("proxy_pool.checker.check_candidate", fake_check_candidate)

    await run_pipeline(settings, batch_size=2)

    refreshed_cache = DeadProxyCache(settings.dead_cache.database_path)
    assert refreshed_cache.should_skip("http", "1.1.1.1:80", "2026-05-22T12:10:00+00:00") is False
    assert refreshed_cache.should_skip("http", "2.2.2.2:80", "2026-05-22T12:10:00+00:00") is True
