# SQLite Dead Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist known-bad proxies in SQLite and skip them for a bounded TTL in future refreshes.

**Architecture:** Add a focused `proxy_pool.dead_cache` module backed by standard-library `sqlite3`, load dead-cache settings from `config.ini`, integrate filtering/recording in `checker.run_pipeline()`, and expose cache stats through `/stats`.

**Tech Stack:** Python 3.12 standard library SQLite, FastAPI, pytest.

---

## File Structure

- Create `proxy_pool/dead_cache.py`: SQLite schema, skip/backoff logic, batch failure/success recording, stats.
- Modify `proxy_pool/config.py`: add `DeadCacheSettings` and settings loading.
- Modify `proxy_pool/checker.py`: filter skipped candidates and update cache after each batch.
- Modify `proxy_pool/api.py`: add dead-cache stats to `/stats`.
- Modify `config.ini`, `README.md`, `docs/api.md`, `docs/configuration.md`, `docs/operations.md`: document behavior.
- Add `tests/test_dead_cache.py`; extend config/checker/api tests.

## Tasks

1. Add dead-cache config defaults and tests.
2. Add SQLite dead-cache module with TDD coverage for schema, skip TTL, success clearing, failure backoff, and stats.
3. Integrate dead-cache into checker batch flow with tests proving skipped candidates are not checked and failures/successes are recorded.
4. Expose `dead_cache` in `/stats` and update docs.
5. Run full verification and Docker smoke.

## Self-Review

- Spec coverage: config, SQLite persistence, checker integration, API stats, docs, and verification are covered.
- Placeholder scan: no TBD/TODO/fill-in placeholders remain.
- Type consistency: use `DeadCacheSettings`, `DeadProxyCache`, and `dead_cache` consistently.
