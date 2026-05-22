from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

from proxy_pool.models import Protocol


@dataclass(frozen=True, slots=True)
class Settings:
    config_path: Path
    timeout: float
    max_connections: int
    sort_by_speed: bool
    save_path: Path
    json_result_filename: str
    save_format: str
    refresh_interval_seconds: int
    sources: dict[Protocol, tuple[str, ...]]

    @property
    def result_path(self) -> Path:
        return self.save_path / self.json_result_filename


def load_config(path: str | Path = "config.ini") -> Settings:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(config_path)

    parser = ConfigParser(interpolation=None)
    parser.read(config_path, encoding="utf-8")

    general = parser["General"]
    save_path_value = general.get("SavePath", "").strip()
    save_path = Path(save_path_value) if save_path_value else config_path.parent

    return Settings(
        config_path=config_path,
        timeout=general.getfloat("Timeout", fallback=10),
        max_connections=general.getint("MaxConnections", fallback=900),
        sort_by_speed=general.getboolean("SortBySpeed", fallback=True),
        save_path=save_path,
        json_result_filename=general.get("JsonResultFilename", fallback="proxies.json"),
        save_format=general.get("SaveFormat", fallback="json"),
        refresh_interval_seconds=general.getint("RefreshIntervalSeconds", fallback=900),
        sources=_load_sources(parser),
    )


def _load_sources(parser: ConfigParser) -> dict[Protocol, tuple[str, ...]]:
    sources: dict[Protocol, tuple[str, ...]] = {}
    for protocol in ("http", "socks4", "socks5"):
        section = protocol.upper()
        if not parser.has_section(section):
            continue
        if not parser.getboolean(section, "Enabled", fallback=True):
            continue

        protocol_sources = tuple(
            source.strip()
            for source in parser.get(section, "Sources", fallback="").splitlines()
            if source.strip()
        )
        if protocol_sources:
            sources[protocol] = protocol_sources

    return sources
