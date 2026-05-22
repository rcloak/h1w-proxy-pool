import pytest

from proxy_pool.checker import _checked_proxy_from_response, build_proxy_json, sort_checked
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
