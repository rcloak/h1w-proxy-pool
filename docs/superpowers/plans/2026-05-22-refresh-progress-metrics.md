# Refresh Progress Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add elapsed runtime and percent-complete metrics to `/stats.current_refresh`.

**Architecture:** Keep scheduler progress snapshots unchanged and enrich `current_refresh` at API response time so elapsed time updates on every `/stats` request. Compute `elapsed_seconds` from `started_at`/`finished_at` and `progress_percent` from `checked`/`total`.

**Tech Stack:** Python 3.12, FastAPI, pytest.

---

## File Structure

- Modify `proxy_pool/api.py`: add helper functions to enrich current refresh metrics before returning `/stats`.
- Modify `tests/test_api.py`: cover running, completed/failed, zero-total, and invalid timestamp behavior.
- Modify `README.md`, `docs/api.md`, `docs/operations.md`: document `elapsed_seconds` and `progress_percent`.

## Task 1: API Progress Metrics

**Files:**
- Modify: `proxy_pool/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add tests to `tests/test_api.py` that set `app.state.current_refresh` and call `/stats`:

```python
def test_stats_adds_running_refresh_metrics(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_document(path, [])
    app = create_app(result_path=path, start_scheduler=False)
    app.state.current_refresh = {
        "status": "running",
        "started_at": "2026-05-22T12:00:00+00:00",
        "finished_at": None,
        "checked": 25,
        "total": 100,
        "alive": 3,
        "current_protocol": "http",
    }

    with TestClient(app) as client:
        response = client.get("/stats")

    current_refresh = response.json()["current_refresh"]
    assert current_refresh["elapsed_seconds"] >= 0
    assert current_refresh["progress_percent"] == 25.0


def test_stats_adds_finished_refresh_metrics(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_document(path, [])
    app = create_app(result_path=path, start_scheduler=False)
    app.state.current_refresh = {
        "status": "idle",
        "started_at": "2026-05-22T12:00:00+00:00",
        "finished_at": "2026-05-22T12:00:05+00:00",
        "checked": 100,
        "total": 100,
        "alive": 5,
        "current_protocol": None,
    }

    with TestClient(app) as client:
        response = client.get("/stats")

    assert response.json()["current_refresh"]["elapsed_seconds"] == 5.0
    assert response.json()["current_refresh"]["progress_percent"] == 100.0
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_api.py::test_stats_adds_running_refresh_metrics tests/test_api.py::test_stats_adds_finished_refresh_metrics -v`

Expected: FAIL because fields are missing.

- [ ] **Step 3: Implement metrics**

In `proxy_pool/api.py`, import `UTC` and `datetime`:

```python
from datetime import UTC, datetime
```

Add helpers:

```python
def _current_refresh_with_metrics(current_refresh: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(current_refresh)
    enriched["elapsed_seconds"] = _refresh_elapsed_seconds(enriched)
    total = enriched.get("total")
    checked = enriched.get("checked")
    if isinstance(total, int) and isinstance(checked, int) and total > 0:
        enriched["progress_percent"] = round((checked / total) * 100.0, 2)
    else:
        enriched["progress_percent"] = 0.0
    return enriched


def _refresh_elapsed_seconds(progress: dict[str, Any]) -> float | None:
    started = _parse_iso_datetime(progress.get("started_at"))
    if started is None:
        return None

    finished = _parse_iso_datetime(progress.get("finished_at"))
    end = finished if finished is not None else datetime.now(UTC)
    return round(max(0.0, (end - started).total_seconds()), 3)


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
```

In `stats()`, return enriched current refresh:

```python
    current_refresh = _current_refresh_with_metrics(current_refresh)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_api.py -v`

Expected: PASS.

## Task 2: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `docs/operations.md`

- [ ] **Step 1: Update docs**

Document these fields in examples and tables:

```json
"elapsed_seconds": 843.2,
"progress_percent": 18.88
```

Use this meaning:
- `elapsed_seconds`: seconds since `started_at` for running refreshes, or `finished_at - started_at` for idle/failed completed refreshes; `null` when timestamps are missing or invalid.
- `progress_percent`: `checked / total * 100`, rounded to two decimals; `0.0` when `total` is zero.

- [ ] **Step 2: Full verification**

Run:

```sh
uv run pytest -v
uv run python -m compileall proxy_pool tests
docker compose build
docker compose up -d --force-recreate
curl -sS --max-time 5 http://localhost:5000/stats
```

Expected: tests/build pass and `/stats.current_refresh` contains `elapsed_seconds` and `progress_percent`.

## Self-Review

- Spec coverage: Task 1 adds API metrics and tests; Task 2 documents and verifies them.
- Placeholder scan: no TBD/TODO/fill-in placeholders remain.
- Type consistency: `elapsed_seconds` and `progress_percent` names are consistent across code, tests, and docs.
