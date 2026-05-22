from pathlib import Path

import pytest

from proxy_pool.config import load_config
from proxy_pool.models import CheckedProxy, checked_proxy_to_item, empty_proxy_document


def test_load_config_reads_general_settings(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
Timeout = 7
MaxConnections = 25
SortBySpeed = no
SavePath =
JsonResultFilename = proxies.json
SaveFormat = json
RefreshIntervalSeconds = 30

[Folders]
proxies = yes
proxies_anonymous = no
proxies_geolocation = no
proxies_geolocation_anonymous = no

[HTTP]
Enabled = yes
Sources =
    https://example.test/http.txt

[SOCKS4]
Enabled = no
Sources =
    https://example.test/socks4.txt

[SOCKS5]
Enabled = yes
Sources =
    https://example.test/socks5.txt
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.timeout == 7
    assert settings.max_connections == 25
    assert settings.sort_by_speed is False
    assert settings.save_path == tmp_path
    assert settings.json_result_filename == "proxies.json"
    assert settings.refresh_interval_seconds == 30
    assert settings.sources == {
        "http": ("https://example.test/http.txt",),
        "socks5": ("https://example.test/socks5.txt",),
    }


def test_load_config_defaults_refresh_interval(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
Timeout = 10
MaxConnections = 800
SortBySpeed = yes
SavePath = /app
JsonResultFilename = proxies.json
SaveFormat = json

[Folders]
proxies = yes
proxies_anonymous = yes
proxies_geolocation = yes
proxies_geolocation_anonymous = yes

[HTTP]
Enabled = no
Sources =

[SOCKS4]
Enabled = no
Sources =

[SOCKS5]
Enabled = no
Sources =
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.refresh_interval_seconds == 900
    assert settings.result_path == Path("/app/proxies.json")


def test_load_config_accepts_fractional_timeout(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
Timeout = 0.5
MaxConnections = 25
SortBySpeed = yes
SavePath =
JsonResultFilename = proxies.json
SaveFormat = json

[HTTP]
Enabled = no
Sources =
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.timeout == 0.5


def test_load_config_treats_omitted_enabled_as_enabled(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
Timeout = 10
MaxConnections = 25
SortBySpeed = yes
SavePath =
JsonResultFilename = proxies.json
SaveFormat = json

[HTTP]
Sources =
    https://example.test/http.txt
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.sources == {"http": ("https://example.test/http.txt",)}


def test_load_config_uses_legacy_general_fallbacks(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
SavePath =

[HTTP]
Enabled = no
Sources =
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.timeout == 10
    assert settings.max_connections == 900
    assert settings.sort_by_speed is True
    assert settings.json_result_filename == "proxies.json"
    assert settings.save_format == "json"
    assert settings.refresh_interval_seconds == 900
    assert settings.result_path == tmp_path / "proxies.json"


def test_empty_proxy_document_returns_v2_schema():
    assert empty_proxy_document(generated_at="2026-05-22T12:00:00Z") == {
        "version": 2,
        "generated_at": "2026-05-22T12:00:00Z",
        "total": 0,
        "items": [],
    }


def test_checked_proxy_to_item_returns_clean_v2_item():
    item = checked_proxy_to_item(
        CheckedProxy(
            endpoint="1.2.3.4:8080",
            source_protocol="http",
            usable_as=("http", "https"),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=90.8,
            success_rate=1.0,
            checks_passed=2,
            checks_failed=0,
            avg_latency_ms=420,
            last_error=None,
            checked_at="2026-05-22T12:00:00Z",
        )
    )

    assert item["endpoint"] == "1.2.3.4:8080"
    assert item["source_protocol"] == "http"
    assert item["usable_as"] == ["http", "https"]
    assert item["quality"]["score"] == 90.8
    assert item["network"]["anonymous"] is True
    assert item["timestamps"]["checked_at"] == "2026-05-22T12:00:00Z"


def test_checked_proxy_to_item_clamps_quality_values():
    item = checked_proxy_to_item(
        CheckedProxy(
            endpoint="1.2.3.4:8080",
            source_protocol="http",
            usable_as=("http",),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=float("inf"),
            success_rate=-1,
            checks_passed=-2,
            checks_failed=-3,
            avg_latency_ms=-420,
            last_error="failed",
            checked_at="2026-05-22T12:00:00Z",
        )
    )

    assert item["quality"] == {
        "score": 0.0,
        "success_rate": 0.0,
        "checks_passed": 0,
        "checks_failed": 0,
        "avg_latency_ms": 0,
        "last_error": "failed",
    }


def test_checked_proxy_requires_v2_constructor_fields():
    with pytest.raises(TypeError):
        CheckedProxy(
            endpoint="1.2.3.4:8080",
            source_protocol="http",
            usable_as=("http",),
        )


@pytest.mark.parametrize("endpoint", ["not-an-endpoint", "1.2.3.4:+80", "1.2.3.4: 80", "1.2.3.4:80\n"])
def test_checked_proxy_to_item_rejects_invalid_endpoint(endpoint: str):
    proxy = CheckedProxy(
        endpoint=endpoint,
        source_protocol="http",
        usable_as=("http",),
        exit_ip="8.8.8.8",
        country_code="US",
        anonymous=True,
        score=90.8,
        success_rate=1.0,
        checks_passed=2,
        checks_failed=0,
        avg_latency_ms=420,
        last_error=None,
        checked_at="2026-05-22T12:00:00Z",
    )

    with pytest.raises(ValueError):
        checked_proxy_to_item(proxy)


def test_checked_proxy_to_item_rejects_zero_port_endpoint():
    proxy = CheckedProxy(
        endpoint="1.2.3.4:0",
        source_protocol="http",
        usable_as=("http",),
        exit_ip="8.8.8.8",
        country_code="US",
        anonymous=True,
        score=90.8,
        success_rate=1.0,
        checks_passed=2,
        checks_failed=0,
        avg_latency_ms=420,
        last_error=None,
        checked_at="2026-05-22T12:00:00Z",
    )

    with pytest.raises(ValueError):
        checked_proxy_to_item(proxy)


def test_load_config_reads_checker_settings(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
SavePath =

[Folders]

[HTTP]
Enabled = no
Sources =

[SOCKS4]
Enabled = no
Sources =

[SOCKS5]
Enabled = no
Sources =

[Checker]
Endpoints =
    http://example.test/ip
    https://example.test/ip
AttemptsPerProxy = 3
RequiredSuccesses = 2
CheckHttp = no
CheckHttps = yes
MinSuccessRate = 0.75
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.checker.endpoints == ("http://example.test/ip", "https://example.test/ip")
    assert settings.checker.attempts_per_proxy == 3
    assert settings.checker.required_successes == 2
    assert settings.checker.check_http is False
    assert settings.checker.check_https is True
    assert settings.checker.min_success_rate == 0.75


def test_load_config_uses_checker_defaults_when_section_missing(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
SavePath =

[Folders]

[HTTP]
Enabled = no
Sources =

[SOCKS4]
Enabled = no
Sources =

[SOCKS5]
Enabled = no
Sources =
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.checker.endpoints == (
        "http://httpbin.org/ip",
        "https://api.ipify.org?format=json",
        "http://ip-api.com/json/?fields=8219",
    )
    assert settings.checker.attempts_per_proxy == 2
    assert settings.checker.required_successes == 1
    assert settings.checker.check_http is True
    assert settings.checker.check_https is True
    assert settings.checker.min_success_rate == 0.5


def test_load_config_uses_checker_defaults_for_malformed_values(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
SavePath =

[HTTP]
Enabled = no
Sources =

[Checker]
Endpoints =
AttemptsPerProxy = invalid
RequiredSuccesses = invalid
CheckHttp = invalid
CheckHttps = invalid
MinSuccessRate = invalid
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.checker.endpoints == (
        "http://httpbin.org/ip",
        "https://api.ipify.org?format=json",
        "http://ip-api.com/json/?fields=8219",
    )
    assert settings.checker.attempts_per_proxy == 2
    assert settings.checker.required_successes == 1
    assert settings.checker.check_http is True
    assert settings.checker.check_https is True
    assert settings.checker.min_success_rate == 0.5


def test_load_config_clamps_checker_numeric_bounds(tmp_path: Path):
    low_config_file = tmp_path / "low.ini"
    low_config_file.write_text(
        """
[General]
SavePath =

[HTTP]
Enabled = no
Sources =

[Checker]
AttemptsPerProxy = 0
RequiredSuccesses = 0
MinSuccessRate = -1
""".strip(),
        encoding="utf-8",
    )
    high_config_file = tmp_path / "high.ini"
    high_config_file.write_text(
        """
[General]
SavePath =

[HTTP]
Enabled = no
Sources =

[Checker]
MinSuccessRate = 2
""".strip(),
        encoding="utf-8",
    )

    low_settings = load_config(low_config_file)
    high_settings = load_config(high_config_file)

    assert low_settings.checker.attempts_per_proxy == 1
    assert low_settings.checker.required_successes == 1
    assert low_settings.checker.min_success_rate == 0.0
    assert high_settings.checker.min_success_rate == 1.0


def test_load_config_enables_http_when_all_checker_capabilities_disabled(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
SavePath =

[HTTP]
Enabled = no
Sources =

[Checker]
CheckHttp = no
CheckHttps = no
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.checker.check_http is True
    assert settings.checker.check_https is False
