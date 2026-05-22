from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast

from proxy_pool.models import ProxyJson, empty_proxy_json


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
            normalized[protocol] = value

    normalized["total_count_of_proxies"] = sum(
        len(normalized[protocol]) for protocol in ("http", "socks4", "socks5")
    )
    return cast(ProxyJson, normalized)


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
