from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from proxy_pool.models import ProxyJson
from proxy_pool.storage import read_proxy_json

router = APIRouter()


def flatten_proxy_json(payload: ProxyJson) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for prototype in ("http", "socks4", "socks5"):
        for item in payload[prototype]:
            rows.append({**item, "prototype": prototype})
    return rows


def apply_filters(
    rows: list[dict[str, Any]],
    prototypes: str | None,
    countrycodes: str | None,
    isanonymous: str | None,
    maxtimeout: float | None,
    minscore: float | None,
    supportshttps: str | None,
    minsuccessrate: float | None,
) -> list[dict[str, Any]]:
    allowed_prototypes = _split_filter(prototypes)
    allowed_countrycodes = _split_filter(countrycodes)
    anonymous_filter = isanonymous.lower() if isanonymous is not None else None
    supports_https_filter = supportshttps.lower() if supportshttps is not None else None

    filtered_rows: list[dict[str, Any]] = []
    for row in rows:
        if allowed_prototypes is not None and row["prototype"].lower() not in allowed_prototypes:
            continue
        if allowed_countrycodes is not None and row["countryCode"].lower() not in allowed_countrycodes:
            continue
        if anonymous_filter is not None and str(row["is_anonymous"]).lower() != anonymous_filter:
            continue
        if maxtimeout is not None and row["timeout"] > maxtimeout:
            continue
        if minscore is not None and float(row.get("score", 0.0)) < minscore:
            continue
        if minsuccessrate is not None and float(row.get("success_rate", 0.0)) < minsuccessrate:
            continue
        if supports_https_filter is not None and str(row.get("supports_https", False)).lower() != supports_https_filter:
            continue
        filtered_rows.append(row)

    return filtered_rows


@router.get("/")
def root(
    request: Request,
    prototypes: str | None = None,
    countrycodes: str | None = None,
    isanonymous: str | None = None,
    maxtimeout: float | None = None,
    minscore: float | None = None,
    supportshttps: str | None = None,
    minsuccessrate: float | None = None,
) -> ProxyJson | list[dict[str, Any]]:
    result_path: Path = request.app.state.result_path
    payload = read_proxy_json(result_path)
    maxtimeout = _validate_finite_filter("maxtimeout", maxtimeout)
    minscore = _validate_finite_filter("minscore", minscore)
    minsuccessrate = _validate_finite_filter("minsuccessrate", minsuccessrate)

    if (
        prototypes is None
        and countrycodes is None
        and isanonymous is None
        and maxtimeout is None
        and minscore is None
        and supportshttps is None
        and minsuccessrate is None
    ):
        return payload

    return apply_filters(
        flatten_proxy_json(payload),
        prototypes,
        countrycodes,
        isanonymous,
        maxtimeout,
        minscore,
        supportshttps,
        minsuccessrate,
    )


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
    return payload


def _split_filter(value: str | None) -> set[str] | None:
    if value is None:
        return None
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _validate_finite_filter(name: str, value: float | None) -> float | None:
    if value is not None and not math.isfinite(value):
        raise HTTPException(status_code=422, detail=f"{name} must be finite")
    return value
