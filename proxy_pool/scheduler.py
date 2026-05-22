from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from proxy_pool.checker import run_pipeline
from proxy_pool.config import Settings
from proxy_pool.models import RefreshProgress, idle_refresh_progress

logger = logging.getLogger(__name__)


async def scheduler_loop(
    settings: Settings,
    stop_event: asyncio.Event,
    on_error: Callable[[Exception], None] | None = None,
    on_success: Callable[[datetime, datetime, dict[str, Any]], None] | None = None,
    on_progress: Callable[[RefreshProgress], None] | None = None,
) -> None:
    while not stop_event.is_set():
        try:
            started = datetime.now(UTC)
            payload = await run_pipeline(settings, on_progress=on_progress)
            finished = datetime.now(UTC)
            if on_success is not None:
                on_success(started, finished, payload)
            if on_progress is not None:
                progress = idle_refresh_progress()
                progress["started_at"] = started.isoformat()
                progress["finished_at"] = finished.isoformat()
                progress["checked"] = int(payload.get("total", 0))
                progress["total"] = int(payload.get("total", 0))
                progress["alive"] = int(payload.get("total", 0))
                on_progress(progress)
        except Exception as exc:
            logger.exception("Proxy refresh failed")
            if on_error is not None:
                on_error(exc)
            if on_progress is not None:
                failed = idle_refresh_progress()
                failed["status"] = "failed"
                failed["finished_at"] = datetime.now(UTC).isoformat()
                on_progress(failed)

        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=settings.refresh_interval_seconds)
