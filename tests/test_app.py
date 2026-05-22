from pathlib import Path

from fastapi.testclient import TestClient

from proxy_pool import app as app_module
from proxy_pool.app import create_app


def test_app_can_disable_scheduler_for_tests(tmp_path: Path):
    app = create_app(result_path=tmp_path / "proxies.json", start_scheduler=False)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert getattr(app.state, "scheduler_task", None) is None


def test_app_starts_scheduler_when_enabled(monkeypatch):
    async def scheduler_loop(settings, stop_event):
        await stop_event.wait()

    monkeypatch.setattr(app_module, "scheduler_loop", scheduler_loop, raising=False)

    app = create_app(start_scheduler=True)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert app.state.scheduler_task is not None
