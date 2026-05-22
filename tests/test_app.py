from pathlib import Path

from fastapi.testclient import TestClient

from proxy_pool import app as app_module
from proxy_pool.app import create_app
from proxy_pool.config import Settings
from proxy_pool import scheduler as scheduler_module


def test_app_can_disable_scheduler_for_tests(tmp_path: Path):
    app = create_app(result_path=tmp_path / "proxies.json", start_scheduler=False)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert getattr(app.state, "scheduler_task", None) is None


def test_app_starts_scheduler_when_enabled(monkeypatch):
    async def scheduler_loop(settings, stop_event, on_error=None):
        await stop_event.wait()

    monkeypatch.setattr(app_module, "scheduler_loop", scheduler_loop, raising=False)

    app = create_app(start_scheduler=True)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert app.state.scheduler_task is not None


async def test_scheduler_records_refresh_errors_and_continues(monkeypatch, tmp_path: Path):
    settings = Settings(
        config_path=tmp_path / "config.ini",
        timeout=1,
        max_connections=1,
        sort_by_speed=True,
        save_path=tmp_path,
        json_result_filename="proxies.json",
        save_format="json",
        refresh_interval_seconds=0,
        sources={},
    )
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


def test_health_reports_scheduler_status_and_last_error(monkeypatch):
    async def scheduler_loop(settings, stop_event, on_error=None):
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
