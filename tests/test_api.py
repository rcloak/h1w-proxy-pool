import importlib
import sys
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from proxy_pool.app import create_app
from proxy_pool.models import ProxyDocument, ProxyItem, empty_proxy_document
from proxy_pool.storage import write_proxy_document


def make_proxy_item(
    endpoint: str,
    *,
    source_protocol: str = "http",
    usable_as: list[str] | None = None,
    score: float = 50.0,
    success_rate: float = 1.0,
    country: str = "US",
    anonymous: bool = True,
    checked_at: str = "2026-05-22T12:00:00Z",
) -> ProxyItem:
    return cast(ProxyItem, {
        "endpoint": endpoint,
        "source_protocol": source_protocol,
        "usable_as": usable_as or ["http"],
        "quality": {
            "score": score,
            "success_rate": success_rate,
            "checks_passed": 1,
            "checks_failed": 0,
            "avg_latency_ms": 200,
            "last_error": None,
        },
        "network": {
            "exit_ip": endpoint.rsplit(":", 1)[0],
            "country_code": country,
            "anonymous": anonymous,
        },
        "timestamps": {"checked_at": checked_at},
    })


def write_document(path: Path, items: list[ProxyItem], generated_at: str = "2026-05-22T12:00:00Z") -> ProxyDocument:
    payload: ProxyDocument = {
        "version": 2,
        "generated_at": generated_at,
        "total": len(items),
        "items": items,
    }
    write_proxy_document(path, payload)
    return payload


def test_proxies_returns_v2_document_shape(tmp_path: Path):
    path = tmp_path / "proxies.json"
    payload = write_document(path, [make_proxy_item("1.2.3.4:80")])

    client = TestClient(create_app(result_path=path, start_scheduler=False))

    assert client.get("/proxies").json() == {"total": 1, "items": payload["items"]}


def test_root_returns_same_v2_shape_as_proxies(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_document(path, [make_proxy_item("1.2.3.4:80")])
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    assert client.get("/").json() == client.get("/proxies").json()


def test_proxies_filters_v2_fields(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_document(
        path,
        [
            make_proxy_item(
                "1.1.1.1:80",
                source_protocol="http",
                usable_as=["http", "https"],
                score=90.0,
                success_rate=1.0,
                country="US",
                anonymous=True,
            ),
            make_proxy_item(
                "2.2.2.2:1080",
                source_protocol="socks5",
                usable_as=["http"],
                score=40.0,
                success_rate=0.5,
                country="DE",
                anonymous=False,
            ),
        ],
    )
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    response = client.get(
        "/proxies?source_protocol=http&usable_as=https&min_score=80&min_success_rate=0.9&country=us&anonymous=true&limit=10"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["endpoint"] == "1.1.1.1:80"


def test_proxies_sort_by_score_and_limits_results(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_document(
        path,
        [
            make_proxy_item("1.1.1.1:80", score=30.0),
            make_proxy_item("2.2.2.2:80", score=90.0),
            make_proxy_item("3.3.3.3:80", score=60.0),
        ],
    )
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    response = client.get("/proxies?limit=2")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [item["endpoint"] for item in response.json()["items"]] == ["2.2.2.2:80", "3.3.3.3:80"]


def test_proxies_caps_limit_at_1000(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_document(path, [make_proxy_item(f"10.0.{index // 255}.{index % 255}:80") for index in range(1001)])
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    response = client.get("/proxies?limit=2000")

    assert response.status_code == 200
    assert response.json()["total"] == 1000
    assert len(response.json()["items"]) == 1000


def test_proxies_rejects_non_positive_limit(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_proxy_document(path, empty_proxy_document())
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    response = client.get("/proxies?limit=0")

    assert response.status_code == 422


def test_proxies_rejects_nan_min_score(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_proxy_document(path, empty_proxy_document())
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    response = client.get("/proxies?min_score=nan")

    assert response.status_code == 422
    assert "min_score must be finite" in response.json()["detail"]


def test_proxies_rejects_infinite_min_success_rate(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_proxy_document(path, empty_proxy_document())
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    response = client.get("/proxies?min_success_rate=inf")

    assert response.status_code == 422
    assert "min_success_rate must be finite" in response.json()["detail"]


def test_stats_returns_v2_counts_and_default_refresh_info(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_document(
        path,
        [
            make_proxy_item("1.1.1.1:80", source_protocol="http", usable_as=["http", "https"]),
            make_proxy_item("2.2.2.2:1080", source_protocol="socks5", usable_as=["http"]),
        ],
        generated_at="2026-05-22T12:00:00Z",
    )
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    response = client.get("/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "by_source_protocol": {"http": 1, "socks4": 0, "socks5": 1},
        "by_capability": {"http": 2, "https": 1},
        "last_refresh": {
            "generated_at": "2026-05-22T12:00:00Z",
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "proxies_alive": 2,
        },
    }


def test_health_reports_storage_status(tmp_path: Path):
    client = TestClient(create_app(result_path=tmp_path / "missing.json", start_scheduler=False))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["storage_exists"] is False


def test_app_factory_importable_without_config_in_cwd(tmp_path: Path, monkeypatch: Any):
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("proxy_pool.app", None)

    app_module = importlib.import_module("proxy_pool.app")
    created_app = app_module.create_app(result_path=tmp_path / "proxies.json", start_scheduler=False)

    assert app_module.app.title == "Proxy Pool"
    assert app_module.app.state.result_path == Path("proxies.json")
    assert app_module.app.state.start_scheduler is False
    assert created_app.state.result_path == tmp_path / "proxies.json"
    assert created_app.state.start_scheduler is False
