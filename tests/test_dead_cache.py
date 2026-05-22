from pathlib import Path

from proxy_pool.dead_cache import DeadProxyCache


NOW = "2026-05-22T12:00:00+00:00"


def test_dead_cache_records_failure_and_skips_until_ttl(tmp_path: Path):
    cache = DeadProxyCache(tmp_path / "proxy_state.sqlite3")

    cache.record_failure("http", "1.2.3.4:80", "TimeoutError", NOW)

    assert cache.should_skip("http", "1.2.3.4:80", "2026-05-22T12:10:00+00:00") is True
    assert cache.should_skip("http", "1.2.3.4:80", "2026-05-22T12:31:00+00:00") is False


def test_dead_cache_uses_protocol_specific_keys(tmp_path: Path):
    cache = DeadProxyCache(tmp_path / "proxy_state.sqlite3")

    cache.record_failure("http", "1.2.3.4:80", "TimeoutError", NOW)

    assert cache.should_skip("http", "1.2.3.4:80", "2026-05-22T12:10:00+00:00") is True
    assert cache.should_skip("socks5", "1.2.3.4:80", "2026-05-22T12:10:00+00:00") is False


def test_dead_cache_increases_backoff_after_repeated_failures(tmp_path: Path):
    cache = DeadProxyCache(tmp_path / "proxy_state.sqlite3")

    cache.record_failure("http", "1.2.3.4:80", "TimeoutError", NOW)
    cache.record_failure("http", "1.2.3.4:80", "TimeoutError", "2026-05-22T12:31:00+00:00")

    assert cache.should_skip("http", "1.2.3.4:80", "2026-05-22T14:00:00+00:00") is True
    assert cache.should_skip("http", "1.2.3.4:80", "2026-05-22T14:32:00+00:00") is False


def test_dead_cache_clears_successful_proxy(tmp_path: Path):
    cache = DeadProxyCache(tmp_path / "proxy_state.sqlite3")
    cache.record_failure("http", "1.2.3.4:80", "TimeoutError", NOW)

    cache.record_success("http", "1.2.3.4:80")

    assert cache.should_skip("http", "1.2.3.4:80", "2026-05-22T12:10:00+00:00") is False


def test_dead_cache_stats_counts_stored_skipped_and_retryable(tmp_path: Path):
    cache = DeadProxyCache(tmp_path / "proxy_state.sqlite3")
    cache.record_failure("http", "1.2.3.4:80", "TimeoutError", NOW)
    cache.record_failure("http", "5.6.7.8:80", "TimeoutError", "2026-05-22T10:00:00+00:00")

    assert cache.stats("2026-05-22T12:10:00+00:00") == {
        "stored": 2,
        "currently_skipped": 1,
        "expired_retryable": 1,
    }


def test_dead_cache_get_skipped_endpoints_returns_active_rows_for_batch(tmp_path: Path):
    cache = DeadProxyCache(tmp_path / "proxy_state.sqlite3")
    cache.record_failure("http", "1.2.3.4:80", "TimeoutError", NOW)
    cache.record_failure("http", "5.6.7.8:80", "TimeoutError", "2026-05-22T10:00:00+00:00")

    assert cache.get_skipped_endpoints(
        "http",
        ["1.2.3.4:80", "5.6.7.8:80", "9.9.9.9:80"],
        "2026-05-22T12:10:00+00:00",
    ) == {"1.2.3.4:80"}


def test_dead_cache_records_batch_results_in_one_operation(tmp_path: Path):
    cache = DeadProxyCache(tmp_path / "proxy_state.sqlite3")
    cache.record_failure("http", "1.2.3.4:80", "TimeoutError", NOW)

    cache.record_batch(
        "http",
        successes=["1.2.3.4:80"],
        failures={"5.6.7.8:80": "check failed", "9.9.9.9:80": "TimeoutError"},
        now="2026-05-22T12:10:00+00:00",
    )

    assert cache.should_skip("http", "1.2.3.4:80", "2026-05-22T12:20:00+00:00") is False
    assert cache.should_skip("http", "5.6.7.8:80", "2026-05-22T12:20:00+00:00") is True
    assert cache.should_skip("http", "9.9.9.9:80", "2026-05-22T12:20:00+00:00") is True
