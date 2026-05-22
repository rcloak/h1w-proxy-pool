from __future__ import annotations

from configparser import ConfigParser, SectionProxy
from dataclasses import dataclass
from pathlib import Path

from proxy_pool.models import Protocol


DEFAULT_CHECK_ENDPOINTS = (
    "http://httpbin.org/ip",
    "https://api.ipify.org?format=json",
    "http://ip-api.com/json/?fields=8219",
)


@dataclass(frozen=True, slots=True)
class CheckerSettings:
    endpoints: tuple[str, ...]
    attempts_per_proxy: int
    required_successes: int
    check_http: bool
    check_https: bool
    min_success_rate: float


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
    checker: CheckerSettings

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
        checker=_load_checker_settings(parser),
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


def _load_checker_settings(parser: ConfigParser) -> CheckerSettings:
    if parser.has_section("Checker"):
        section = parser["Checker"]
        endpoints = tuple(
            line.strip() for line in section.get("Endpoints", "").splitlines() if line.strip()
        )
        if not endpoints:
            endpoints = DEFAULT_CHECK_ENDPOINTS
        check_http = _get_checker_bool(section, "CheckHttp", True)
        check_https = _get_checker_bool(section, "CheckHttps", True)
        if not check_http and not check_https:
            check_http = True
        return CheckerSettings(
            endpoints=endpoints,
            attempts_per_proxy=max(1, _get_checker_int(section, "AttemptsPerProxy", 2)),
            required_successes=max(1, _get_checker_int(section, "RequiredSuccesses", 1)),
            check_http=check_http,
            check_https=check_https,
            min_success_rate=min(1.0, max(0.0, _get_checker_float(section, "MinSuccessRate", 0.5))),
        )
    return CheckerSettings(
        endpoints=DEFAULT_CHECK_ENDPOINTS,
        attempts_per_proxy=2,
        required_successes=1,
        check_http=True,
        check_https=True,
        min_success_rate=0.5,
    )


def _get_checker_int(section: SectionProxy, option: str, fallback: int) -> int:
    try:
        return section.getint(option, fallback=fallback)
    except ValueError:
        return fallback


def _get_checker_float(section: SectionProxy, option: str, fallback: float) -> float:
    try:
        return section.getfloat(option, fallback=fallback)
    except ValueError:
        return fallback


def _get_checker_bool(section: SectionProxy, option: str, fallback: bool) -> bool:
    try:
        return section.getboolean(option, fallback=fallback)
    except ValueError:
        return fallback
