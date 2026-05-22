from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from proxy_pool.dead_cache import DeadProxyCache
from proxy_pool.models import ProxyItem, idle_refresh_progress
from proxy_pool.storage import read_proxy_document

router = APIRouter()


@router.get("/")
def root(
    request: Request,
    source_protocol: str | None = None,
    usable_as: str | None = None,
    min_score: float | None = None,
    min_success_rate: float | None = None,
    country: str | None = None,
    anonymous: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    return proxies(request, source_protocol, usable_as, min_score, min_success_rate, country, anonymous, limit)


@router.get("/proxies")
def proxies(
    request: Request,
    source_protocol: str | None = None,
    usable_as: str | None = None,
    min_score: float | None = None,
    min_success_rate: float | None = None,
    country: str | None = None,
    anonymous: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    result_path: Path = request.app.state.result_path
    payload = read_proxy_document(result_path)
    min_score = _validate_finite_filter("min_score", min_score)
    min_success_rate = _validate_finite_filter("min_success_rate", min_success_rate)
    limit = _validate_limit(limit)

    items = _apply_filters(
        payload["items"],
        source_protocol=source_protocol,
        usable_as=usable_as,
        min_score=min_score,
        min_success_rate=min_success_rate,
        country=country,
        anonymous=anonymous,
    )
    items.sort(key=lambda item: (-item["quality"]["score"], item["quality"]["avg_latency_ms"], item["endpoint"]))
    if limit is not None:
        items = items[:limit]
    return {"total": len(items), "items": items}


@router.get("/stats")
def stats(request: Request) -> dict[str, Any]:
    result_path: Path = request.app.state.result_path
    payload = read_proxy_document(result_path)
    by_source_protocol = {"http": 0, "socks4": 0, "socks5": 0}
    by_capability = {"http": 0, "https": 0}

    for item in payload["items"]:
        by_source_protocol[item["source_protocol"]] += 1
        for capability in item["usable_as"]:
            by_capability[capability] += 1

    last_refresh = getattr(request.app.state, "last_refresh", None)
    if not isinstance(last_refresh, dict):
        last_refresh = {
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "proxies_alive": 0,
        }

    current_refresh = getattr(request.app.state, "current_refresh", None)
    if not isinstance(current_refresh, dict):
        current_refresh = idle_refresh_progress()
    current_refresh = _current_refresh_with_metrics(current_refresh)

    return {
        "total": payload["total"],
        "by_source_protocol": by_source_protocol,
        "by_capability": by_capability,
        "last_refresh": last_refresh,
        "current_refresh": current_refresh,
        "dead_cache": _dead_cache_stats(request),
    }


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    result_path: Path = request.app.state.result_path
    payload: dict[str, object] = {
        "status": "ok",
        "storage_path": str(result_path),
        "storage_exists": result_path.exists(),
    }
    if hasattr(request.app.state, "scheduler_task"):
        task = request.app.state.scheduler_task
        payload["scheduler_running"] = task is not None and not task.done()
    if hasattr(request.app.state, "last_scheduler_error"):
        payload["last_scheduler_error"] = request.app.state.last_scheduler_error
    current_refresh = getattr(request.app.state, "current_refresh", None)
    if isinstance(current_refresh, dict):
        payload["refresh_running"] = current_refresh.get("status") == "running"
    return payload


def _current_refresh_with_metrics(current_refresh: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(current_refresh)
    enriched["elapsed_seconds"] = _refresh_elapsed_seconds(enriched)

    checked = enriched.get("checked")
    total = enriched.get("total")
    if isinstance(checked, int) and isinstance(total, int) and total > 0:
        enriched["progress_percent"] = round((checked / total) * 100.0, 2)
    else:
        enriched["progress_percent"] = 0.0
    return enriched


def _dead_cache_stats(request: Request) -> dict[str, object]:
    settings = getattr(request.app.state, "settings", None)
    dead_cache_settings = getattr(settings, "dead_cache", None)
    if dead_cache_settings is None or not getattr(dead_cache_settings, "enabled", False):
        return {"enabled": False, "stored": 0, "currently_skipped": 0, "expired_retryable": 0}

    now = datetime.now(UTC).isoformat()
    stats = DeadProxyCache(dead_cache_settings.database_path).stats(now)
    return {"enabled": True, **stats}


def _refresh_elapsed_seconds(progress: dict[str, Any]) -> float | None:
    started_at = _parse_iso_datetime(progress.get("started_at"))
    if started_at is None:
        return None

    if progress.get("status") == "running":
        end = datetime.now(UTC)
    else:
        end = _parse_iso_datetime(progress.get("finished_at"))
        if end is None:
            return None
    return round(max(0.0, (end - started_at).total_seconds()), 3)


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _apply_filters(
    items: list[ProxyItem],
    *,
    source_protocol: str | None,
    usable_as: str | None,
    min_score: float | None,
    min_success_rate: float | None,
    country: str | None,
    anonymous: str | None,
) -> list[ProxyItem]:
    source_protocol_filter = source_protocol.lower() if source_protocol is not None else None
    usable_as_filter = usable_as.lower() if usable_as is not None else None
    country_filter = country.lower() if country is not None else None
    anonymous_filter = _parse_bool_filter("anonymous", anonymous)

    filtered_items: list[ProxyItem] = []
    for item in items:
        if source_protocol_filter is not None and item["source_protocol"].lower() != source_protocol_filter:
            continue
        if usable_as_filter is not None and usable_as_filter not in [capability.lower() for capability in item["usable_as"]]:
            continue
        if min_score is not None and item["quality"]["score"] < min_score:
            continue
        if min_success_rate is not None and item["quality"]["success_rate"] < min_success_rate:
            continue
        if country_filter is not None and item["network"]["country_code"].lower() != country_filter:
            continue
        if anonymous_filter is not None and item["network"]["anonymous"] is not anonymous_filter:
            continue
        filtered_items.append(item)
    return filtered_items


def _parse_bool_filter(name: str, value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise HTTPException(status_code=422, detail=f"{name} must be true or false")


def _validate_finite_filter(name: str, value: float | None) -> float | None:
    if value is not None and not math.isfinite(value):
        raise HTTPException(status_code=422, detail=f"{name} must be finite")
    return value


def _validate_limit(value: int | None) -> int | None:
    if value is None:
        return None
    if value <= 0:
        raise HTTPException(status_code=422, detail="limit must be a positive integer")
    return min(value, 1000)
