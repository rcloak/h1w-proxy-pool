from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast

from proxy_pool.models import ProxyJson, ProxyJsonItem, empty_proxy_json


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
                normalized_item for item in value if (normalized_item := _normalize_proxy_item(item)) is not None
            ]

    normalized["total_count_of_proxies"] = sum(
        len(normalized[protocol]) for protocol in ("http", "socks4", "socks5")
    )
    return cast(ProxyJson, normalized)


def _normalize_proxy_item(item: object) -> ProxyJsonItem | None:
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

    return {
        "address": address,
        "countryCode": country_code,
        "is_anonymous": is_anonymous,
        "timeout": float(timeout),
    }


def write_proxy_json(path: Path, payload: ProxyJson) -> None:
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
            json.dump(cast(dict[str, Any], payload), temp_file)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
