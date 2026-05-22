# Visible Refresh Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long proxy refreshes observable by writing partial verified proxy results during batch processing and exposing current refresh progress through the API.

**Architecture:** Keep the current file-based v2 storage model. Add a small refresh progress model, make `run_pipeline()` process candidates in batches and call a progress callback, then let the scheduler/app state expose progress through `/stats` and `/health`.

**Tech Stack:** Python 3.12, FastAPI, aiohttp/aiohttp-socks, pytest, Docker Compose.

---

## File Structure

- Modify `proxy_pool/models.py`: add `RefreshProgress` typed dict and `idle_refresh_progress()` helper.
- Modify `proxy_pool/checker.py`: add batch helper, progress callback type, and partial writes in `run_pipeline()`.
- Modify `proxy_pool/scheduler.py`: pass progress callback into `run_pipeline()` and emit failed progress on unexpected exceptions.
- Modify `proxy_pool/app.py`: initialize and update `app.state.current_refresh`; expose callbacks to scheduler.
- Modify `proxy_pool/api.py`: include `current_refresh` in `/stats` and `refresh_running` in `/health`.
- Modify `tests/test_checker.py`: cover partial writes and progress updates from batched pipeline execution.
- Modify `tests/test_app.py`: cover app/scheduler progress state, `/stats`, and `/health` fields.
- Modify `docs/api.md`, `docs/operations.md`, `README.md`: document partial results and progress fields.

## Task 1: Refresh Progress Model

**Files:**
- Modify: `proxy_pool/models.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append these tests to `tests/test_config.py`:

```python
from proxy_pool.models import idle_refresh_progress


def test_idle_refresh_progress_returns_stable_shape():
    result = idle_refresh_progress()

    assert result == {
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "checked": 0,
        "total": 0,
        "alive": 0,
        "current_protocol": None,
    }


def test_idle_refresh_progress_returns_new_dict_each_time():
    first = idle_refresh_progress()
    second = idle_refresh_progress()
    first["status"] = "running"

    assert second["status"] == "idle"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py::test_idle_refresh_progress_returns_stable_shape tests/test_config.py::test_idle_refresh_progress_returns_new_dict_each_time -v`

Expected: FAIL with `ImportError` or missing `idle_refresh_progress`.

- [ ] **Step 3: Implement the progress model**

In `proxy_pool/models.py`, add this after `ProxyDocument`:

```python
class RefreshProgress(TypedDict):
    status: Literal["idle", "running", "failed"]
    started_at: str | None
    finished_at: str | None
    checked: int
    total: int
    alive: int
    current_protocol: Protocol | None


def idle_refresh_progress() -> RefreshProgress:
    return {
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "checked": 0,
        "total": 0,
        "alive": 0,
        "current_protocol": None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py::test_idle_refresh_progress_returns_stable_shape tests/test_config.py::test_idle_refresh_progress_returns_new_dict_each_time -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```sh
git add proxy_pool/models.py tests/test_config.py
git commit -m "feat: add refresh progress model"
```

## Task 2: Batch Partial Writes In Checker

**Files:**
- Modify: `proxy_pool/checker.py`
- Test: `tests/test_checker.py`

- [ ] **Step 1: Write failing tests for batched partial writes**

Add imports in `tests/test_checker.py`:

```python
from pathlib import Path

from proxy_pool.checker import run_pipeline
from proxy_pool.config import DEFAULT_CHECK_ENDPOINTS, Settings
from proxy_pool.storage import read_proxy_document
```

Append this helper and test to `tests/test_checker.py`:

```python
def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        config_path=tmp_path / "config.ini",
        timeout=1,
        max_connections=2,
        sort_by_speed=True,
        save_path=tmp_path,
        json_result_filename="proxies.json",
        save_format="json",
        refresh_interval_seconds=60,
        sources={"http": ("https://example.test/http.txt",)},
        checker=CheckerSettings(
            endpoints=DEFAULT_CHECK_ENDPOINTS,
            attempts_per_proxy=1,
            required_successes=1,
            check_http=True,
            check_https=False,
            min_success_rate=0.5,
        ),
    )


async def test_run_pipeline_writes_partial_documents_after_each_batch(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path)
    candidates = {
        "http": {
            ProxyCandidate(address="1.1.1.1:80", ip="1.1.1.1"),
            ProxyCandidate(address="2.2.2.2:80", ip="2.2.2.2"),
            ProxyCandidate(address="3.3.3.3:80", ip="3.3.3.3"),
        }
    }
    writes: list[int] = []

    async def fake_collect_candidates(sources):
        return candidates

    async def fake_check_candidate(candidate, protocol, timeout, semaphore, checker, checked_at):
        if candidate.address == "2.2.2.2:80":
            return None
        return CheckedProxy(
            endpoint=candidate.address,
            source_protocol=protocol,
            usable_as=("http",),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=90.0,
            success_rate=1.0,
            checks_passed=1,
            checks_failed=0,
            avg_latency_ms=100,
            last_error=None,
            checked_at=checked_at,
        )

    def fake_write_proxy_document(path, payload):
        writes.append(payload["total"])
        from proxy_pool.storage import write_proxy_document as real_write_proxy_document

        real_write_proxy_document(path, payload)

    monkeypatch.setattr("proxy_pool.checker.collect_candidates", fake_collect_candidates)
    monkeypatch.setattr("proxy_pool.checker.check_candidate", fake_check_candidate)
    monkeypatch.setattr("proxy_pool.checker.write_proxy_document", fake_write_proxy_document)

    payload = await run_pipeline(settings, batch_size=2)

    assert writes == [1, 2]
    assert payload["total"] == 2
    assert read_proxy_document(settings.result_path)["total"] == 2
```

- [ ] **Step 2: Write failing test for progress callback**

Append this test to `tests/test_checker.py`:

```python
async def test_run_pipeline_reports_progress_for_batches(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path)
    candidates = {
        "http": {
            ProxyCandidate(address="1.1.1.1:80", ip="1.1.1.1"),
            ProxyCandidate(address="2.2.2.2:80", ip="2.2.2.2"),
            ProxyCandidate(address="3.3.3.3:80", ip="3.3.3.3"),
        }
    }
    progress_updates = []

    async def fake_collect_candidates(sources):
        return candidates

    async def fake_check_candidate(candidate, protocol, timeout, semaphore, checker, checked_at):
        return CheckedProxy(
            endpoint=candidate.address,
            source_protocol=protocol,
            usable_as=("http",),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=90.0,
            success_rate=1.0,
            checks_passed=1,
            checks_failed=0,
            avg_latency_ms=100,
            last_error=None,
            checked_at=checked_at,
        )

    monkeypatch.setattr("proxy_pool.checker.collect_candidates", fake_collect_candidates)
    monkeypatch.setattr("proxy_pool.checker.check_candidate", fake_check_candidate)

    await run_pipeline(settings, progress_updates.append, batch_size=2)

    assert progress_updates[0]["status"] == "running"
    assert progress_updates[0]["checked"] == 0
    assert progress_updates[0]["total"] == 3
    assert [update["checked"] for update in progress_updates[1:]] == [2, 3]
    assert progress_updates[-1]["alive"] == 3
    assert progress_updates[-1]["current_protocol"] == "http"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_checker.py::test_run_pipeline_writes_partial_documents_after_each_batch tests/test_checker.py::test_run_pipeline_reports_progress_for_batches -v`

Expected: FAIL because `run_pipeline()` does not accept `batch_size` or progress callback.

- [ ] **Step 4: Implement batch helpers and progress callback**

Modify `proxy_pool/checker.py` imports:

```python
from collections.abc import Callable, Iterable, Mapping, Sequence
```

Add `RefreshProgress` import:

```python
    RefreshProgress,
```

Add constants/types after imports:

```python
DEFAULT_BATCH_SIZE = 500
ProgressCallback = Callable[[RefreshProgress], None]
```

Add helper before `run_pipeline()`:

```python
def _candidate_batches(candidates: Sequence[ProxyCandidate], batch_size: int) -> Iterable[Sequence[ProxyCandidate]]:
    for index in range(0, len(candidates), batch_size):
        yield candidates[index:index + batch_size]
```

Replace `run_pipeline()` with:

```python
async def run_pipeline(
    settings: Settings,
    on_progress: ProgressCallback | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ProxyDocument:
    candidates = await collect_candidates(settings.sources)
    semaphore = asyncio.Semaphore(settings.max_connections)
    checked: list[CheckedProxy] = []
    checked_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    started_at = datetime.now(UTC).isoformat()
    total_candidates = sum(len(protocol_candidates) for protocol_candidates in candidates.values())
    checked_count = 0
    effective_batch_size = max(1, batch_size)

    def emit_progress(status: str, current_protocol: Protocol | None) -> None:
        if on_progress is None:
            return
        on_progress(
            {
                "status": status,
                "started_at": started_at,
                "finished_at": None,
                "checked": checked_count,
                "total": total_candidates,
                "alive": len(checked),
                "current_protocol": current_protocol,
            }
        )

    emit_progress("running", None)

    for protocol, protocol_candidates in candidates.items():
        ordered_candidates = sorted(protocol_candidates, key=lambda candidate: _natural_address_key(candidate.address))
        for batch in _candidate_batches(ordered_candidates, effective_batch_size):
            results = await asyncio.gather(
                *(
                    check_candidate(
                        candidate,
                        protocol,
                        settings.timeout,
                        semaphore,
                        settings.checker,
                        checked_at,
                    )
                    for candidate in batch
                )
            )
            checked.extend(result for result in results if result is not None)
            checked_count += len(batch)
            sorted_proxies = sort_checked(checked, settings.sort_by_speed)
            payload = build_proxy_document(sorted_proxies, generated_at=checked_at)
            write_proxy_document(settings.result_path, payload)
            emit_progress("running", protocol)

    sorted_proxies = sort_checked(checked, settings.sort_by_speed)
    payload = build_proxy_document(sorted_proxies, generated_at=checked_at)
    write_proxy_document(settings.result_path, payload)
    return payload
```

- [ ] **Step 5: Run task tests**

Run: `uv run pytest tests/test_checker.py::test_run_pipeline_writes_partial_documents_after_each_batch tests/test_checker.py::test_run_pipeline_reports_progress_for_batches -v`

Expected: PASS.

- [ ] **Step 6: Run checker test file**

Run: `uv run pytest tests/test_checker.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```sh
git add proxy_pool/checker.py tests/test_checker.py
git commit -m "feat: write partial proxy refresh results"
```

## Task 3: Scheduler And App Progress State

**Files:**
- Modify: `proxy_pool/scheduler.py`
- Modify: `proxy_pool/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing scheduler progress test**

Append this test to `tests/test_app.py`:

```python
async def test_scheduler_forwards_refresh_progress(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path, refresh_interval_seconds=0)
    stop_event = scheduler_module.asyncio.Event()
    progress_updates = []

    async def run_pipeline(settings, on_progress=None):
        if on_progress is not None:
            on_progress(
                {
                    "status": "running",
                    "started_at": "2026-05-22T12:00:00+00:00",
                    "finished_at": None,
                    "checked": 1,
                    "total": 2,
                    "alive": 1,
                    "current_protocol": "http",
                }
            )
        stop_event.set()
        return {"version": 2, "generated_at": "2026-05-22T12:00:00Z", "total": 1, "items": []}

    monkeypatch.setattr(scheduler_module, "run_pipeline", run_pipeline)

    await scheduler_module.scheduler_loop(
        settings,
        stop_event,
        on_progress=progress_updates.append,
    )

    assert progress_updates == [
        {
            "status": "running",
            "started_at": "2026-05-22T12:00:00+00:00",
            "finished_at": None,
            "checked": 1,
            "total": 2,
            "alive": 1,
            "current_protocol": "http",
        }
    ]
```

- [ ] **Step 2: Write failing app progress state test**

Append this test to `tests/test_app.py`:

```python
def test_app_exposes_current_refresh_progress(monkeypatch, tmp_path: Path):
    settings = make_settings(tmp_path)
    refreshed = Event()

    async def scheduler_loop(settings, stop_event, on_error=None, on_success=None, on_progress=None):
        if on_progress is not None:
            on_progress(
                {
                    "status": "running",
                    "started_at": "2026-05-22T12:00:00+00:00",
                    "finished_at": None,
                    "checked": 10,
                    "total": 100,
                    "alive": 3,
                    "current_protocol": "http",
                }
            )
        refreshed.set()
        await stop_event.wait()

    monkeypatch.setattr(app_module, "scheduler_loop", scheduler_loop)

    app = create_app(result_path=tmp_path / "proxies.json", start_scheduler=False)
    app.state.settings = settings
    app.state.start_scheduler = True

    with TestClient(app) as client:
        deadline = monotonic() + 2
        while not refreshed.is_set() and monotonic() < deadline:
            client.get("/health")
        stats = client.get("/stats").json()
        health = client.get("/health").json()

    assert stats["current_refresh"] == {
        "status": "running",
        "started_at": "2026-05-22T12:00:00+00:00",
        "finished_at": None,
        "checked": 10,
        "total": 100,
        "alive": 3,
        "current_protocol": "http",
    }
    assert health["refresh_running"] is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_app.py::test_scheduler_forwards_refresh_progress tests/test_app.py::test_app_exposes_current_refresh_progress -v`

Expected: FAIL because `scheduler_loop()` does not accept `on_progress` and API does not expose progress yet.

- [ ] **Step 4: Implement scheduler progress callback**

Modify `proxy_pool/scheduler.py` imports:

```python
from proxy_pool.models import RefreshProgress, idle_refresh_progress
```

Change `scheduler_loop()` signature:

```python
async def scheduler_loop(
    settings: Settings,
    stop_event: asyncio.Event,
    on_error: Callable[[Exception], None] | None = None,
    on_success: Callable[[datetime, datetime, dict[str, Any]], None] | None = None,
    on_progress: Callable[[RefreshProgress], None] | None = None,
) -> None:
```

Change pipeline call:

```python
payload = await run_pipeline(settings, on_progress=on_progress)
```

After `on_success`, set idle progress:

```python
            if on_progress is not None:
                progress = idle_refresh_progress()
                progress["started_at"] = started.isoformat()
                progress["finished_at"] = finished.isoformat()
                progress["checked"] = int(payload.get("total", 0))
                progress["total"] = int(payload.get("total", 0))
                progress["alive"] = int(payload.get("total", 0))
                on_progress(progress)
```

Inside `except`, after `on_error`, add:

```python
            if on_progress is not None:
                failed = idle_refresh_progress()
                failed["status"] = "failed"
                failed["finished_at"] = datetime.now(UTC).isoformat()
                on_progress(failed)
```

- [ ] **Step 5: Implement app state callbacks**

Modify `proxy_pool/app.py` import:

```python
from proxy_pool.models import RefreshProgress, idle_refresh_progress
```

In `lifespan()`, after `last_refresh` initialization:

```python
    app.state.current_refresh = idle_refresh_progress()
```

Inside scheduler setup, add callback:

```python
        def record_refresh_progress(progress: RefreshProgress) -> None:
            app.state.current_refresh = dict(progress)
```

Pass callback to `scheduler_loop()`:

```python
                on_progress=record_refresh_progress,
```

In `create_app()`, after `last_refresh` initialization:

```python
    app.state.current_refresh = idle_refresh_progress()
```

- [ ] **Step 6: Implement API progress fields**

Modify `proxy_pool/api.py` imports:

```python
from proxy_pool.models import ProxyItem, idle_refresh_progress
```

In `stats()`, before return:

```python
    current_refresh = getattr(request.app.state, "current_refresh", None)
    if not isinstance(current_refresh, dict):
        current_refresh = idle_refresh_progress()
```

Add to return payload:

```python
        "current_refresh": current_refresh,
```

In `health()`, before return:

```python
    current_refresh = getattr(request.app.state, "current_refresh", None)
    if isinstance(current_refresh, dict):
        payload["refresh_running"] = current_refresh.get("status") == "running"
```

- [ ] **Step 7: Run app tests**

Run: `uv run pytest tests/test_app.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```sh
git add proxy_pool/scheduler.py proxy_pool/app.py proxy_pool/api.py tests/test_app.py
git commit -m "feat: expose refresh progress state"
```

## Task 4: API Tests And Documentation

**Files:**
- Modify: `tests/test_api.py`
- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `docs/operations.md`

- [ ] **Step 1: Write API tests for progress fields**

Append these tests to `tests/test_api.py`:

```python
def test_stats_includes_idle_current_refresh(client):
    response = client.get("/stats")

    assert response.status_code == 200
    assert response.json()["current_refresh"] == {
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "checked": 0,
        "total": 0,
        "alive": 0,
        "current_protocol": None,
    }


def test_health_reports_refresh_running(client):
    client.app.state.current_refresh = {
        "status": "running",
        "started_at": "2026-05-22T12:00:00+00:00",
        "finished_at": None,
        "checked": 10,
        "total": 100,
        "alive": 3,
        "current_protocol": "http",
    }

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["refresh_running"] is True
```

- [ ] **Step 2: Run API tests**

Run: `uv run pytest tests/test_api.py::test_stats_includes_idle_current_refresh tests/test_api.py::test_health_reports_refresh_running -v`

Expected: PASS after Task 3.

- [ ] **Step 3: Update README**

In `README.md`, in the `GET /stats` JSON example, add `current_refresh` after `last_refresh`:

```json
  "current_refresh": {
    "status": "running",
    "started_at": "2026-05-22T12:00:00+00:00",
    "finished_at": null,
    "checked": 1500,
    "total": 82669,
    "alive": 123,
    "current_protocol": "http"
  }
```

In the `GET /health` example, add:

```json
  "refresh_running": true
```

Add this paragraph near the API summary:

```markdown
During a long refresh, `/proxies` returns the latest partial verified result file. `current_refresh` in `/stats` shows how many candidates have been checked and how many verified proxies are currently available.
```

- [ ] **Step 4: Update API docs**

In `docs/api.md`, update the `/stats` example with `current_refresh`, and add this field table:

```markdown
`current_refresh` fields:

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | `idle`, `running`, or `failed`. |
| `started_at` | string or null | Start timestamp for the active refresh. |
| `finished_at` | string or null | Finish timestamp when idle after a completed or failed refresh. |
| `checked` | integer | Candidate count processed so far in the active refresh. |
| `total` | integer | Total candidates collected for the active refresh. |
| `alive` | integer | Verified proxies found so far in the active refresh. |
| `current_protocol` | string or null | Protocol currently being processed: `http`, `socks4`, or `socks5`. |
```

Update the `/health` example and field table to include `refresh_running`.

- [ ] **Step 5: Update operations docs**

In `docs/operations.md`, add this to troubleshooting:

```markdown
During long refreshes, watch progress with:

```sh
curl http://localhost:5000/stats
```

`current_refresh.checked` should increase as batches complete. `/proxies` returns the latest partial verified proxy file, so `total` can grow before the refresh finishes.
```

- [ ] **Step 6: Run docs/API tests**

Run: `uv run pytest tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```sh
git add tests/test_api.py README.md docs/api.md docs/operations.md
git commit -m "docs: document visible refresh progress"
```

## Task 5: Full Verification And Docker Smoke

**Files:**
- No source edits expected.

- [ ] **Step 1: Run full tests**

Run: `uv run pytest -v`

Expected: all tests pass.

- [ ] **Step 2: Run compile check**

Run: `uv run python -m compileall proxy_pool tests`

Expected: no compile errors.

- [ ] **Step 3: Build Docker image**

Run: `docker compose build`

Expected: build succeeds.

- [ ] **Step 4: Restart service**

Run: `docker compose up -d --force-recreate`

Expected: service starts and port `5000` is published.

- [ ] **Step 5: Verify API progress appears before full refresh completes**

Run:

```sh
for i in $(seq 1 30); do
  curl -sS --max-time 5 http://localhost:5000/stats
  echo
  sleep 10
done
```

Expected: `current_refresh.status` is `running`, `current_refresh.checked` increases above `0`, and `/health` returns `refresh_running: true` while refresh is active.

- [ ] **Step 6: Verify partial proxy file/API shape**

Run:

```sh
curl -sS --max-time 5 http://localhost:5000/proxies?limit=5
curl -sS --max-time 5 http://localhost:5000/health
```

Expected: `/proxies` returns `{ "total": number, "items": [...] }` without error even during refresh. `total` may be `0` if no live proxies have passed yet, but storage should exist after the first batch completes.

- [ ] **Step 7: Check git status**

Run: `git status --short`

Expected: no uncommitted source/test/doc changes unless intentionally left for user review.

## Self-Review

- Spec coverage: Batch partial writes are Task 2; progress callback and app state are Task 3; API fields and docs are Task 4; Docker/runtime verification is Task 5.
- Placeholder scan: no TBD/TODO/fill-in placeholders remain.
- Type consistency: plan uses `RefreshProgress`, `idle_refresh_progress`, `current_refresh`, and `refresh_running` consistently across models, checker, scheduler, app, API, and tests.
