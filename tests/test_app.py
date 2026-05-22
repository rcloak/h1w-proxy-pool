from pathlib import Path
from threading import Event
from time import monotonic

from fastapi.testclient import TestClient

from proxy_pool import app as app_module
from proxy_pool.app import create_app
from proxy_pool.config import CheckerSettings, DEFAULT_CHECK_ENDPOINTS, Settings
from proxy_pool import scheduler as scheduler_module
from proxy_pool.storage import write_proxy_document


def make_settings(tmp_path: Path, refresh_interval_seconds: int = 60) -> Settings:
    return Settings(
        config_path=tmp_path / "config.ini",
        timeout=1,
        max_connections=1,
        sort_by_speed=True,
        save_path=tmp_path,
        json_result_filename="proxies.json",
        save_format="json",
        refresh_interval_seconds=refresh_interval_seconds,
        sources={},
        checker=CheckerSettings(
            endpoints=DEFAULT_CHECK_ENDPOINTS,
            attempts_per_proxy=2,
            required_successes=1,
            check_http=True,
            check_https=True,
            min_success_rate=0.5,
        ),
    )


def test_app_can_disable_scheduler_for_tests(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_proxy_document(
        path,
        {
            "version": 2,
            "generated_at": "2026-05-22T12:00:00Z",
            "total": 1,
            "items": [
                {
                    "endpoint": "1.2.3.4:80",
                    "source_protocol": "http",
                    "usable_as": ["http"],
                    "quality": {
                        "score": 50.0,
                        "success_rate": 1.0,
                        "checks_passed": 1,
                        "checks_failed": 0,
                        "avg_latency_ms": 200,
                        "last_error": None,
                    },
                    "network": {"exit_ip": "1.2.3.4", "country_code": "US", "anonymous": True},
                    "timestamps": {"checked_at": "2026-05-22T12:00:00Z"},
                }
            ],
        },
    )
    app = create_app(result_path=path, start_scheduler=False)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/").json()["items"][0]["endpoint"] == "1.2.3.4:80"
        assert getattr(app.state, "scheduler_task", None) is None


def test_app_starts_scheduler_when_enabled(monkeypatch):
    async def scheduler_loop(settings, stop_event, on_error=None, on_success=None):
        await stop_event.wait()

    monkeypatch.setattr(app_module, "scheduler_loop", scheduler_loop, raising=False)

    app = create_app(start_scheduler=True)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert app.state.scheduler_task is not None


async def test_scheduler_records_refresh_errors_and_continues(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path, refresh_interval_seconds=0)
    stop_event = scheduler_module.asyncio.Event()
    errors: list[str] = []
    calls = 0

    async def run_pipeline(settings):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("refresh failed")
        stop_event.set()
        return {}

    monkeypatch.setattr(scheduler_module, "run_pipeline", run_pipeline)

    await scheduler_module.scheduler_loop(
        settings,
        stop_event,
        on_error=lambda exc: errors.append(str(exc)),
    )

    assert calls == 2
    assert errors == ["refresh failed"]


async def test_scheduler_records_success_metadata(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path, refresh_interval_seconds=0)
    stop_event = scheduler_module.asyncio.Event()
    successes = []
    payload = {"version": 2, "generated_at": "2026-05-22T12:00:00Z", "total": 2, "items": []}

    async def run_pipeline(settings):
        stop_event.set()
        return payload

    monkeypatch.setattr(scheduler_module, "run_pipeline", run_pipeline)

    await scheduler_module.scheduler_loop(
        settings,
        stop_event,
        on_success=lambda started, finished, payload: successes.append((started, finished, payload)),
    )

    started, finished, result = successes[0]
    assert started <= finished
    assert result is payload


def test_app_records_successful_refresh_metadata(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path)
    refreshed = Event()
    payload = {"version": 2, "generated_at": "2026-05-22T12:00:00Z", "total": 2, "items": []}

    async def run_pipeline(settings):
        refreshed.set()
        return payload

    monkeypatch.setattr(scheduler_module, "run_pipeline", run_pipeline)

    app = create_app(result_path=tmp_path / "proxies.json", start_scheduler=False)
    app.state.settings = settings
    app.state.start_scheduler = True

    with TestClient(app) as client:
        deadline = monotonic() + 2
        while not refreshed.is_set() and monotonic() < deadline:
            client.get("/health")

        stats = client.get("/stats").json()

    assert stats["last_refresh"]["started_at"] is not None
    assert stats["last_refresh"]["finished_at"] is not None
    assert stats["last_refresh"]["duration_seconds"] >= 0
    assert stats["last_refresh"]["proxies_alive"] == 2


def test_health_reports_scheduler_status_and_last_error(monkeypatch):
    async def scheduler_loop(settings, stop_event, on_error=None, on_success=None):
        if on_error is not None:
            on_error(RuntimeError("refresh failed"))
        await stop_event.wait()

    monkeypatch.setattr(app_module, "scheduler_loop", scheduler_loop)

    app = create_app(start_scheduler=True)

    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["scheduler_running"] is True
        assert response.json()["last_scheduler_error"] == "refresh failed"
