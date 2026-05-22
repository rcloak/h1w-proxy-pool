from __future__ import annotations

import json
import os
import tempfile
from ipaddress import ip_address
from math import isfinite
from pathlib import Path
from typing import Any, cast

from proxy_pool.models import (
    Capability,
    Protocol,
    ProxyDocument,
    ProxyItem,
    ProxyJson,
    ProxyJsonItem,
    empty_proxy_document,
    empty_proxy_json,
)


def read_proxy_document(path: Path) -> ProxyDocument:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_proxy_document()

    if not isinstance(payload, dict) or payload.get("version") != 2:
        return empty_proxy_document()

    generated_at = payload.get("generated_at")
    result = empty_proxy_document(generated_at=generated_at if isinstance(generated_at, str) else "")
    items = payload.get("items")
    if isinstance(items, list):
        result["items"] = [normalized for item in items if (normalized := _normalize_proxy_item(item)) is not None]
    result["total"] = len(result["items"])
    return result


def _normalize_proxy_item(item: object) -> ProxyItem | None:
    if not isinstance(item, dict):
        return None

    endpoint = item.get("endpoint")
    source_protocol = item.get("source_protocol")
    quality = item.get("quality")
    network = item.get("network")
    timestamps = item.get("timestamps")

    if not isinstance(endpoint, str) or not endpoint:
        return None
    if source_protocol not in ("http", "socks4", "socks5"):
        return None
    if not isinstance(quality, dict) or not isinstance(network, dict) or not isinstance(timestamps, dict):
        return None

    usable_as = _normalize_capabilities(item.get("usable_as"))
    if usable_as is None:
        return None
    exit_ip = network.get("exit_ip")
    country_code = network.get("country_code")
    anonymous = network.get("anonymous")
    checked_at = timestamps.get("checked_at")

    if not isinstance(exit_ip, str) or not _valid_ip(exit_ip):
        return None
    if not isinstance(country_code, str):
        return None
    if not isinstance(anonymous, bool):
        return None

    last_error = quality.get("last_error")
    return {
        "endpoint": endpoint,
        "source_protocol": cast(Protocol, source_protocol),
        "usable_as": usable_as,
        "quality": {
            "score": _number(quality.get("score"), 0.0, minimum=0.0, maximum=100.0),
            "success_rate": _number(quality.get("success_rate"), 0.0, minimum=0.0, maximum=1.0),
            "checks_passed": _int(quality.get("checks_passed"), 0, minimum=0),
            "checks_failed": _int(quality.get("checks_failed"), 0, minimum=0),
            "avg_latency_ms": _int(quality.get("avg_latency_ms"), 0, minimum=0),
            "last_error": last_error if isinstance(last_error, str) or last_error is None else str(last_error),
        },
        "network": {
            "exit_ip": exit_ip,
            "country_code": country_code,
            "anonymous": anonymous,
        },
        "timestamps": {"checked_at": checked_at if isinstance(checked_at, str) else ""},
    }


def _normalize_capabilities(value: object) -> list[Capability] | None:
    if not isinstance(value, list):
        return None

    result: list[Capability] = []
    for item in value:
        if item not in ("http", "https"):
            return None
        if item not in result:
            result.append(cast(Capability, item))
    if not result:
        return None
    return result


def write_proxy_document(path: Path, payload: ProxyDocument) -> None:
    generated_at = payload.get("generated_at", "")
    normalized = empty_proxy_document(generated_at=generated_at if isinstance(generated_at, str) else "")
    normalized["items"] = [normalized_item for item in payload.get("items", []) if (normalized_item := _normalize_proxy_item(item))]
    normalized["total"] = len(normalized["items"])
    _write_json_atomic(path, cast(dict[str, Any], normalized))


def _valid_ip(value: str) -> bool:
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def read_proxy_json(path: Path) -> ProxyJson:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_proxy_json()

    if not isinstance(payload, dict):
        return empty_proxy_json()

    normalized = empty_proxy_json()
    for protocol in ("http", "socks4", "socks5"):
        value = payload.get(protocol)
        if isinstance(value, list):
            normalized[protocol] = [
                normalized_item for item in value if (normalized_item := _normalize_proxy_json_item(item)) is not None
            ]

    normalized["total_count_of_proxies"] = sum(
        len(normalized[protocol]) for protocol in ("http", "socks4", "socks5")
    )
    return cast(ProxyJson, normalized)


def _normalize_proxy_json_item(item: object) -> ProxyJsonItem | None:
    if not isinstance(item, dict):
        return None

    address = item.get("address")
    country_code = item.get("countryCode")
    is_anonymous = item.get("is_anonymous")
    timeout = item.get("timeout")

    if not isinstance(address, str):
        return None
    if not isinstance(country_code, str):
        return None
    if not isinstance(is_anonymous, bool):
        return None
    if isinstance(timeout, bool) or not isinstance(timeout, int | float):
        return None
    timeout_float = float(timeout)

    supports_http = item.get("supports_http")
    supports_https = item.get("supports_https")
    last_error = item.get("last_error")
    checked_at = item.get("checked_at")

    return {
        "address": address,
        "countryCode": country_code,
        "is_anonymous": is_anonymous,
        "timeout": timeout_float,
        "score": _number(item.get("score"), 0.0, minimum=0.0, maximum=100.0),
        "success_rate": _number(item.get("success_rate"), 0.0, minimum=0.0, maximum=1.0),
        "success_count": _int(item.get("success_count"), 0),
        "failure_count": _int(item.get("failure_count"), 0),
        "supports_http": supports_http if isinstance(supports_http, bool) else False,
        "supports_https": supports_https if isinstance(supports_https, bool) else False,
        "avg_timeout": _number(item.get("avg_timeout"), timeout_float),
        "last_error": last_error if isinstance(last_error, str) or last_error is None else str(last_error),
        "checked_at": checked_at if isinstance(checked_at, str) else "",
    }


def write_proxy_json(path: Path, payload: ProxyJson) -> None:
    _write_json_atomic(path, cast(dict[str, Any], payload))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(payload, temp_file)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _number(value: object, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    result = float(value)
    if not isfinite(result):
        return default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _int(value: object, default: int, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    if not isfinite(float(value)):
        return default
    result = int(value)
    if minimum is not None:
        result = max(minimum, result)
    return result
