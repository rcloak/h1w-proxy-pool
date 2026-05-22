import asyncio

import pytest

from proxy_pool.checker import (
    CheckAttempt,
    _checked_proxy_from_response,
    aggregate_attempts,
    build_attempt_plan,
    build_proxy_json,
    calculate_score,
    check_candidate,
    endpoint_supports_capability,
    extract_observed_ip,
    sort_checked,
)
from proxy_pool.config import CheckerSettings
from proxy_pool.models import CheckedProxy, ProxyCandidate


def test_sort_checked_sorts_by_timeout():
    slow = CheckedProxy(address="1.2.3.4:80", country_code="US", is_anonymous=True, timeout=1.1)
    fast = CheckedProxy(address="5.6.7.8:1080", country_code="DE", is_anonymous=False, timeout=0.2)

    result = sort_checked([slow, fast], sort_by_speed=True)

    assert result == [fast, slow]


def test_sort_checked_sorts_by_natural_address():
    high_port = CheckedProxy(address="1.2.3.4:100", country_code="US", is_anonymous=True, timeout=0.1)
    later_ip = CheckedProxy(address="1.2.3.10:80", country_code="US", is_anonymous=True, timeout=0.1)
    low_port = CheckedProxy(address="1.2.3.4:80", country_code="US", is_anonymous=True, timeout=0.1)

    result = sort_checked([high_port, later_ip, low_port], sort_by_speed=False)

    assert result == [low_port, high_port, later_ip]


def test_checked_proxy_from_response_builds_proxy_from_valid_data():
    candidate = ProxyCandidate(address="1.2.3.4:80", ip="1.2.3.4")

    result = _checked_proxy_from_response(
        candidate,
        {"query": "1.2.3.4", "countryCode": "US"},
        0.2,
    )

    assert result == CheckedProxy(
        address="1.2.3.4:80",
        country_code="US",
        is_anonymous=False,
        timeout=0.2,
    )


@pytest.mark.parametrize(
    "data",
    [
        {"countryCode": "US"},
        {"query": "", "countryCode": "US"},
        {"query": 123, "countryCode": "US"},
        {"query": "1.2.3.4"},
        {"query": "1.2.3.4", "countryCode": ""},
        {"query": "1.2.3.4", "countryCode": None},
    ],
)
def test_checked_proxy_from_response_rejects_malformed_data(data):
    candidate = ProxyCandidate(address="1.2.3.4:80", ip="1.2.3.4")

    result = _checked_proxy_from_response(candidate, data, 0.2)

    assert result is None


def test_build_proxy_json_preserves_schema_and_counts():
    result = build_proxy_json(
        {
            "http": [CheckedProxy(address="1.2.3.4:80", country_code="US", is_anonymous=True, timeout=0.2)],
            "socks4": [],
            "socks5": [CheckedProxy(address="5.6.7.8:1080", country_code="DE", is_anonymous=False, timeout=1.1)],
        }
    )

    assert result["total_count_of_proxies"] == 2
    assert result["http"] == [
        {
            "address": "1.2.3.4:80",
            "countryCode": "US",
            "is_anonymous": True,
            "timeout": 0.2,
            "score": 0.0,
            "success_rate": 0.0,
            "success_count": 0,
            "failure_count": 0,
            "supports_http": False,
            "supports_https": False,
            "avg_timeout": 0.2,
            "last_error": None,
            "checked_at": "",
        }
    ]
    assert result["socks4"] == []
    assert result["socks5"] == [
        {
            "address": "5.6.7.8:1080",
            "countryCode": "DE",
            "is_anonymous": False,
            "timeout": 1.1,
            "score": 0.0,
            "success_rate": 0.0,
            "success_count": 0,
            "failure_count": 0,
            "supports_http": False,
            "supports_https": False,
            "avg_timeout": 1.1,
            "last_error": None,
            "checked_at": "",
        }
    ]


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
        candidate_ip="1.2.3.4",
        attempts=attempts,
        required_successes=1,
        min_success_rate=0.5,
        checked_at="2026-05-22T12:00:00Z",
    )

    assert proxy is not None
    assert proxy.success_count == 2
    assert proxy.failure_count == 1
    assert proxy.success_rate == 2 / 3
    assert proxy.supports_http is True
    assert proxy.supports_https is True
    assert proxy.avg_timeout == 0.3
    assert proxy.timeout == 0.3
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
