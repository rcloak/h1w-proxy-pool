from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from proxy_pool.models import Protocol


class DeadCacheStats(TypedDict):
    stored: int
    currently_skipped: int
    expired_retryable: int


BACKOFF_SECONDS = (30 * 60, 2 * 60 * 60, 6 * 60 * 60, 24 * 60 * 60)
SQLITE_PARAM_LIMIT = 900


def _chunk_list[T](items: list[T], chunk_size: int = SQLITE_PARAM_LIMIT) -> list[list[T]]:
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


class DeadProxyCache:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def should_skip(self, source_protocol: Protocol, endpoint: str, now: str) -> bool:
        return endpoint in self.get_skipped_endpoints(source_protocol, [endpoint], now)

    def get_skipped_endpoints(self, source_protocol: Protocol, endpoints: list[str], now: str) -> set[str]:
        if not endpoints:
            return set()
        now_dt = _parse_timestamp(now) or datetime.now(UTC)
        skipped: set[str] = set()
        with self._connect() as connection:
            for chunk in _chunk_list(endpoints, SQLITE_PARAM_LIMIT):
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT endpoint FROM proxy_failures
                    WHERE source_protocol = ?
                    AND endpoint IN ({placeholders})
                    AND skip_until > ?
                    """,
                    (source_protocol, *chunk, now_dt.isoformat()),
                ).fetchall()
                skipped.update(str(row["endpoint"]) for row in rows)
        return skipped
    def record_failure(self, source_protocol: Protocol, endpoint: str, last_error: str | None, now: str) -> None:
        existing = self._fetch(source_protocol, endpoint)
        fail_count = int(existing["fail_count"]) + 1 if existing is not None else 1
        now_dt = _parse_timestamp(now) or datetime.now(UTC)
        skip_until = now_dt + timedelta(seconds=_backoff_seconds(fail_count))

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO proxy_failures (
                    source_protocol, endpoint, fail_count, last_failed_at, last_error, skip_until
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_protocol, endpoint) DO UPDATE SET
                    fail_count = excluded.fail_count,
                    last_failed_at = excluded.last_failed_at,
                    last_error = excluded.last_error,
                    skip_until = excluded.skip_until
                """,
                (source_protocol, endpoint, fail_count, now_dt.isoformat(), last_error, skip_until.isoformat()),
            )

    def record_success(self, source_protocol: Protocol, endpoint: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM proxy_failures WHERE source_protocol = ? AND endpoint = ?",
                (source_protocol, endpoint),
            )

    def record_batch(
        self,
        source_protocol: Protocol,
        *,
        successes: list[str],
        failures: dict[str, str | None],
        now: str,
    ) -> None:
        now_dt = _parse_timestamp(now) or datetime.now(UTC)
        failure_endpoints = list(failures)
        existing_counts: dict[str, int] = {}
        with self._connect() as connection:
            if failure_endpoints:
                for chunk in _chunk_list(failure_endpoints, SQLITE_PARAM_LIMIT):
                    placeholders = ",".join("?" for _ in chunk)
                    rows = connection.execute(
                        f"""
                        SELECT endpoint, fail_count FROM proxy_failures
                        WHERE source_protocol = ? AND endpoint IN ({placeholders})
                        """,
                        (source_protocol, *chunk),
                    ).fetchall()
                    for row in rows:
                        existing_counts[str(row["endpoint"])] = int(row["fail_count"])
            if successes:
                connection.executemany(
                    "DELETE FROM proxy_failures WHERE source_protocol = ? AND endpoint = ?",
                    [(source_protocol, endpoint) for endpoint in successes],
                )

            if failures:
                rows_to_upsert = []
                for endpoint, error in failures.items():
                    fail_count = existing_counts.get(endpoint, 0) + 1
                    skip_until = now_dt + timedelta(seconds=_backoff_seconds(fail_count))
                    rows_to_upsert.append(
                        (source_protocol, endpoint, fail_count, now_dt.isoformat(), error, skip_until.isoformat())
                    )
                connection.executemany(
                    """
                    INSERT INTO proxy_failures (
                        source_protocol, endpoint, fail_count, last_failed_at, last_error, skip_until
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_protocol, endpoint) DO UPDATE SET
                        fail_count = excluded.fail_count,
                        last_failed_at = excluded.last_failed_at,
                        last_error = excluded.last_error,
                        skip_until = excluded.skip_until
                    """,
                    rows_to_upsert,
                )

    def stats(self, now: str) -> DeadCacheStats:
        now_dt = _parse_timestamp(now) or datetime.now(UTC)
        with self._connect() as connection:
            stored = connection.execute("SELECT COUNT(*) FROM proxy_failures").fetchone()[0]
            skipped = connection.execute(
                "SELECT COUNT(*) FROM proxy_failures WHERE skip_until > ?",
                (now_dt.isoformat(),),
            ).fetchone()[0]
        return {
            "stored": int(stored),
            "currently_skipped": int(skipped),
            "expired_retryable": int(stored) - int(skipped),
        }

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS proxy_failures (
                    source_protocol TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    fail_count INTEGER NOT NULL,
                    last_failed_at TEXT NOT NULL,
                    last_error TEXT,
                    skip_until TEXT NOT NULL,
                    PRIMARY KEY (source_protocol, endpoint)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_proxy_failures_skip_until ON proxy_failures (skip_until)"
            )

    def _fetch(self, source_protocol: Protocol, endpoint: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT fail_count, skip_until FROM proxy_failures WHERE source_protocol = ? AND endpoint = ?",
                (source_protocol, endpoint),
            ).fetchone()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

def _backoff_seconds(fail_count: int) -> int:
    return BACKOFF_SECONDS[min(max(1, fail_count), len(BACKOFF_SECONDS)) - 1]


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
