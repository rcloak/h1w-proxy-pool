from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress

from proxy_pool.checker import run_pipeline
from proxy_pool.config import Settings

logger = logging.getLogger(__name__)


async def scheduler_loop(
    settings: Settings,
    stop_event: asyncio.Event,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    while not stop_event.is_set():
        try:
            await run_pipeline(settings)
        except Exception as exc:
            logger.exception("Proxy refresh failed")
            if on_error is not None:
                on_error(exc)

        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=settings.refresh_interval_seconds)
