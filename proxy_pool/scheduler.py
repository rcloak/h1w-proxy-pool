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
        last_progress = idle_refresh_progress()
        progress_emitted = False

        def record_progress(progress: RefreshProgress) -> None:
            nonlocal last_progress, progress_emitted
            progress_emitted = True
            last_progress = dict(progress)
            if on_progress is not None:
                on_progress(dict(progress))

        try:
            started = datetime.now(UTC)
            payload = await run_pipeline(settings, on_progress=record_progress)
            finished = datetime.now(UTC)
            if on_success is not None:
                on_success(started, finished, payload)
            if on_progress is not None:
                progress = dict(last_progress)
                progress["status"] = "idle"
                progress["started_at"] = progress["started_at"] or started.isoformat()
                progress["finished_at"] = finished.isoformat()
                if not progress_emitted:
                    payload_total = int(payload.get("total", 0))
                    progress["checked"] = payload_total
                    progress["total"] = payload_total
                    progress["alive"] = payload_total
                progress["current_protocol"] = None
                on_progress(progress)
        except Exception as exc:
            logger.exception("Proxy refresh failed")
            if on_error is not None:
                on_error(exc)
            if on_progress is not None:
                failed = dict(last_progress)
                failed["status"] = "failed"
                failed["started_at"] = failed["started_at"] or started.isoformat()
                failed["finished_at"] = datetime.now(UTC).isoformat()
                on_progress(failed)

        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=settings.refresh_interval_seconds)
