from proxy_pool.checker import build_proxy_json
from proxy_pool.models import CheckedProxy


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
        {"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": True, "timeout": 0.2}
    ]
    assert result["socks4"] == []
    assert result["socks5"] == [
        {"address": "5.6.7.8:1080", "countryCode": "DE", "is_anonymous": False, "timeout": 1.1}
    ]
