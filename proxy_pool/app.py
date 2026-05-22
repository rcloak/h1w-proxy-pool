from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from proxy_pool.api import router
from proxy_pool.config import load_config
from proxy_pool.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.last_scheduler_error = None

    if app.state.start_scheduler and app.state.settings is not None:
        def record_scheduler_error(exc: Exception) -> None:
            app.state.last_scheduler_error = str(exc)

        stop_event = asyncio.Event()
        app.state.scheduler_stop_event = stop_event
        app.state.scheduler_task = asyncio.create_task(
            scheduler_loop(
                app.state.settings,
                stop_event,
                on_error=record_scheduler_error,
            )
        )
    else:
        app.state.scheduler_task = None

    try:
        yield
    finally:
        stop_event = getattr(app.state, "scheduler_stop_event", None)
        if stop_event is not None:
            stop_event.set()

        task = getattr(app.state, "scheduler_task", None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def create_app(result_path: str | Path | None = None, start_scheduler: bool = True) -> FastAPI:
    app = FastAPI(title="Proxy Pool", lifespan=lifespan)

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
