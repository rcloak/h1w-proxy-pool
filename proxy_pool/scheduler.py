from __future__ import annotations

import asyncio
from contextlib import suppress

from proxy_pool.checker import run_pipeline
from proxy_pool.config import Settings


async def scheduler_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await run_pipeline(settings)
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=settings.refresh_interval_seconds)
