import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from proxy_pool.app import create_app
from proxy_pool.models import empty_proxy_json
from proxy_pool.storage import write_proxy_json


def test_root_returns_full_json_without_filters(tmp_path: Path):
    payload = empty_proxy_json()
    payload["http"].append(
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
    )
    payload["total_count_of_proxies"] = 1
    result_path = tmp_path / "proxies.json"
    write_proxy_json(result_path, payload)

    client = TestClient(create_app(result_path=result_path, start_scheduler=False))

    assert client.get("/").json() == payload


def test_root_filters_by_protocol_country_anonymity_and_timeout(tmp_path: Path):
    payload = empty_proxy_json()
    payload["http"] = [
        {"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": True, "timeout": 0.2},
        {"address": "2.2.2.2:80", "countryCode": "DE", "is_anonymous": True, "timeout": 0.4},
    ]
    payload["socks5"] = [
        {"address": "5.6.7.8:1080", "countryCode": "US", "is_anonymous": False, "timeout": 1.2},
    ]
    payload["total_count_of_proxies"] = 3
    result_path = tmp_path / "proxies.json"
    write_proxy_json(result_path, payload)

    client = TestClient(create_app(result_path=result_path, start_scheduler=False))
    response = client.get("/?prototypes=http&countrycodes=us&isanonymous=true&maxtimeout=0.3")

    assert response.status_code == 200
    assert response.json() == [
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
            "prototype": "http",
        }
    ]


def test_root_filters_by_quality_fields(tmp_path: Path):
    payload = empty_proxy_json()
    payload["http"] = [
        {
            "address": "1.1.1.1:80",
            "countryCode": "US",
            "is_anonymous": True,
            "timeout": 0.1,
            "score": 95.0,
            "success_rate": 1.0,
            "success_count": 4,
            "failure_count": 0,
            "supports_http": True,
            "supports_https": True,
            "avg_timeout": 0.1,
            "last_error": None,
            "checked_at": "2026-05-22T12:00:00Z",
        },
        {
            "address": "2.2.2.2:80",
            "countryCode": "US",
            "is_anonymous": True,
            "timeout": 0.2,
            "score": 70.0,
            "success_rate": 0.75,
            "success_count": 3,
            "failure_count": 1,
            "supports_http": True,
            "supports_https": False,
            "avg_timeout": 0.2,
            "last_error": None,
            "checked_at": "2026-05-22T12:00:00Z",
        },
    ]
    payload["total_count_of_proxies"] = 2
    result_path = tmp_path / "proxies.json"
    write_proxy_json(result_path, payload)

    client = TestClient(create_app(result_path=result_path, start_scheduler=False))
    response = client.get("/?minscore=90&supportshttps=true&minsuccessrate=0.9")

    assert response.status_code == 200
    assert response.json() == [
        {
            "address": "1.1.1.1:80",
            "countryCode": "US",
            "is_anonymous": True,
            "timeout": 0.1,
            "score": 95.0,
            "success_rate": 1.0,
            "success_count": 4,
            "failure_count": 0,
            "supports_http": True,
            "supports_https": True,
            "avg_timeout": 0.1,
            "last_error": None,
            "checked_at": "2026-05-22T12:00:00Z",
            "prototype": "http",
        }
    ]


def test_root_filter_without_maxtimeout_does_not_crash(tmp_path: Path):
    payload = empty_proxy_json()
    payload["http"].append({"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": True, "timeout": 0.2})
    payload["total_count_of_proxies"] = 1
    result_path = tmp_path / "proxies.json"
    write_proxy_json(result_path, payload)

    client = TestClient(create_app(result_path=result_path, start_scheduler=False))

    assert client.get("/?prototypes=http").status_code == 200


def test_health_reports_storage_status(tmp_path: Path):
    client = TestClient(create_app(result_path=tmp_path / "missing.json", start_scheduler=False))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["storage_exists"] is False


def test_app_factory_importable_without_config_in_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("proxy_pool.app", None)

    app_module = importlib.import_module("proxy_pool.app")
    created_app = app_module.create_app(result_path=tmp_path / "proxies.json", start_scheduler=False)

    assert app_module.app.title == "Proxy Pool"
    assert app_module.app.state.result_path == Path("proxies.json")
    assert app_module.app.state.start_scheduler is False
    assert created_app.state.result_path == tmp_path / "proxies.json"
    assert created_app.state.start_scheduler is False
