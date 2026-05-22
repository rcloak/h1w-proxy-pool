from pathlib import Path

from proxy_pool.models import empty_proxy_json
from proxy_pool.storage import read_proxy_json, write_proxy_json


def test_read_proxy_json_returns_empty_for_missing_file(tmp_path: Path):
    assert read_proxy_json(tmp_path / "missing.json") == empty_proxy_json()


def test_read_proxy_json_returns_empty_for_malformed_file(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text("{", encoding="utf-8")

    assert read_proxy_json(target) == empty_proxy_json()


def test_read_proxy_json_drops_invalid_proxy_items(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        '{"http": ["bad", {"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": true, "timeout": 0.5}], "socks4": [{"address": "missing-timeout"}], "socks5": []}',
        encoding="utf-8",
    )

    result = read_proxy_json(target)

    assert result["total_count_of_proxies"] == 1
    assert result["http"] == [
        {
            "address": "1.2.3.4:80",
            "countryCode": "US",
            "is_anonymous": True,
            "timeout": 0.5,
            "score": 0.0,
            "success_rate": 0.0,
            "success_count": 0,
            "failure_count": 0,
            "supports_http": False,
            "supports_https": False,
            "avg_timeout": 0.5,
            "last_error": None,
            "checked_at": "",
        }
    ]
    assert result["socks4"] == []
    assert result["socks5"] == []


def test_read_proxy_json_preserves_quality_fields(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        '{"http": [{"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": true, "timeout": 0.5, "score": 90.0, "success_rate": 1.0, "success_count": 4, "failure_count": 0, "supports_http": true, "supports_https": true, "avg_timeout": 0.5, "last_error": null, "checked_at": "2026-05-22T12:00:00Z"}], "socks4": [], "socks5": []}',
        encoding="utf-8",
    )

    result = read_proxy_json(target)

    item = result["http"][0]
    assert item["score"] == 90.0
    assert item["success_rate"] == 1.0
    assert item["success_count"] == 4
    assert item["failure_count"] == 0
    assert item["supports_http"] is True
    assert item["supports_https"] is True
    assert item["avg_timeout"] == 0.5
    assert item["last_error"] is None
    assert item["checked_at"] == "2026-05-22T12:00:00Z"


def test_read_proxy_json_accepts_legacy_items_without_quality_fields(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        '{"http": [{"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": true, "timeout": 0.5}], "socks4": [], "socks5": []}',
        encoding="utf-8",
    )

    result = read_proxy_json(target)

    assert result["total_count_of_proxies"] == 1
    item = result["http"][0]
    assert item["address"] == "1.2.3.4:80"
    assert item["score"] == 0.0
    assert item["success_rate"] == 0.0
    assert item["success_count"] == 0
    assert item["failure_count"] == 0
    assert item["supports_http"] is False
    assert item["supports_https"] is False
    assert item["avg_timeout"] == 0.5
    assert item["last_error"] is None
    assert item["checked_at"] == ""


def test_read_proxy_json_clamps_quality_metric_ranges(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        '{"http": [{"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": true, "timeout": 0.5, "score": -10, "success_rate": -1}, {"address": "2.2.2.2:80", "countryCode": "US", "is_anonymous": true, "timeout": 0.7, "score": 999, "success_rate": 2}], "socks4": [], "socks5": []}',
        encoding="utf-8",
    )

    result = read_proxy_json(target)

    low_item = result["http"][0]
    high_item = result["http"][1]
    assert low_item["score"] == 0.0
    assert low_item["success_rate"] == 0.0
    assert high_item["score"] == 100.0
    assert high_item["success_rate"] == 1.0


def test_read_proxy_json_uses_defaults_for_non_finite_quality_floats(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        '{"http": [{"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": true, "timeout": 0.5, "score": Infinity, "success_rate": NaN, "avg_timeout": Infinity}], "socks4": [], "socks5": []}',
        encoding="utf-8",
    )

    result = read_proxy_json(target)

    item = result["http"][0]
    assert item["score"] == 0.0
    assert item["success_rate"] == 0.0
    assert item["avg_timeout"] == 0.5


def test_write_proxy_json_writes_schema_atomically(tmp_path: Path):
    target = tmp_path / "proxies.json"
    payload = empty_proxy_json()
    payload["http"].append(
        {
            "address": "1.2.3.4:80",
            "countryCode": "US",
            "is_anonymous": True,
            "timeout": 0.5,
            "score": 0.0,
            "success_rate": 0.0,
            "success_count": 0,
            "failure_count": 0,
            "supports_http": False,
            "supports_https": False,
            "avg_timeout": 0.5,
            "last_error": None,
            "checked_at": "",
        }
    )
    payload["total_count_of_proxies"] = 1

    write_proxy_json(target, payload)

    assert read_proxy_json(target) == payload
    assert not list(tmp_path.glob("*.tmp"))
