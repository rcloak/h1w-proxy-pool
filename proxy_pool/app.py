from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI

from proxy_pool.api import router
from proxy_pool.config import load_config


def create_app(result_path: str | Path | None = None, start_scheduler: bool = True) -> FastAPI:
    app = FastAPI(title="Proxy Pool")

    if result_path is None:
        settings = load_config()
        app.state.settings = settings
        app.state.result_path = settings.result_path
    else:
        app.state.settings = None
        app.state.result_path = Path(result_path)

    app.state.start_scheduler = start_scheduler
    app.include_router(router)
    return app


def _create_module_app() -> FastAPI:
    try:
        return create_app()
    except FileNotFoundError:
        return create_app(result_path=Path("proxies.json"), start_scheduler=False)


app = _create_module_app()


def main() -> None:
    uvicorn.run("proxy_pool.app:app", host="0.0.0.0", port=5000)
