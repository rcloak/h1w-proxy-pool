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
    assert result["http"] == [{"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": True, "timeout": 0.5}]
    assert result["socks4"] == []
    assert result["socks5"] == []


def test_write_proxy_json_writes_schema_atomically(tmp_path: Path):
    target = tmp_path / "proxies.json"
    payload = empty_proxy_json()
    payload["http"].append({"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": True, "timeout": 0.5})
    payload["total_count_of_proxies"] = 1

    write_proxy_json(target, payload)

    assert read_proxy_json(target) == payload
    assert not list(tmp_path.glob("*.tmp"))
