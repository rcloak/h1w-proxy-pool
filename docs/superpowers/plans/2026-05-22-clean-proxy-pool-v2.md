# Clean Proxy Pool v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy grouped proxy JSON/API with a clean v2 proxy list that exposes verified source protocol, usable capabilities, quality, network identity, stats, and stable filters.

**Architecture:** Introduce v2 storage/model helpers in `proxy_pool.models` and `proxy_pool.storage`, refactor checker aggregation to emit v2 items directly, then simplify API routes to `/proxies`, `/`, `/stats`, and `/health`. Documentation and tests should describe v2 only; v1 compatibility is not required.

**Tech Stack:** Python 3.12+, UV, FastAPI, aiohttp, aiohttp-socks, pytest, Docker.

---

## File Map

- Modify `proxy_pool/models.py`: replace v1 `ProxyJson` shape with v2 document/item typed structures and serialization helpers.
- Modify `proxy_pool/storage.py`: read/write v2 storage only; malformed or non-v2 files return empty v2 document.
- Modify `proxy_pool/checker.py`: aggregate attempts into v2 proxy items and build v2 storage.
- Modify `proxy_pool/api.py`: expose `/proxies`, root v2 response, `/stats`, v2 filters, and health.
- Modify `tests/test_storage.py`, `tests/test_checker.py`, `tests/test_api.py`, `tests/test_app.py`, `tests/test_config.py`: update to v2 expectations.
- Modify docs: `README.md`, `docs/api.md`, `docs/architecture.md`, `docs/configuration.md`, `docs/operations.md`, `.planning/ROADMAP.md`.

## Task 1: V2 Models And Storage

**Files:**
- Modify: `proxy_pool/models.py`
- Modify: `proxy_pool/storage.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Replace storage tests with v2 expectations**

Update `tests/test_storage.py` to cover the v2 document shape:

```python
from pathlib import Path

from proxy_pool.models import empty_proxy_document
from proxy_pool.storage import read_proxy_document, write_proxy_document


def test_read_proxy_document_returns_empty_for_missing_file(tmp_path: Path):
    assert read_proxy_document(tmp_path / "missing.json") == empty_proxy_document()


def test_read_proxy_document_returns_empty_for_malformed_file(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text("{", encoding="utf-8")

    assert read_proxy_document(target) == empty_proxy_document()


def test_read_proxy_document_returns_empty_for_non_v2_file(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text('{"total_count_of_proxies": 1, "http": [], "socks4": [], "socks5": []}', encoding="utf-8")

    assert read_proxy_document(target) == empty_proxy_document()


def test_write_proxy_document_writes_v2_schema_atomically(tmp_path: Path):
    target = tmp_path / "proxies.json"
    payload = empty_proxy_document(generated_at="2026-05-22T12:00:00Z")
    payload["items"].append(
        {
            "endpoint": "1.2.3.4:8080",
            "source_protocol": "http",
            "usable_as": ["http", "https"],
            "quality": {
                "score": 90.8,
                "success_rate": 1.0,
                "checks_passed": 2,
                "checks_failed": 0,
                "avg_latency_ms": 420,
                "last_error": None,
            },
            "network": {
                "exit_ip": "8.8.8.8",
                "country_code": "US",
                "anonymous": True,
            },
            "timestamps": {"checked_at": "2026-05-22T12:00:00Z"},
        }
    )
    payload["total"] = 1

    write_proxy_document(target, payload)

    assert read_proxy_document(target) == payload
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Replace model tests with v2 serialization tests**

In `tests/test_config.py`, replace tests that assert old `empty_proxy_json()` or `checked_proxy_to_json()` output with:

```python
from proxy_pool.models import CheckedProxy, checked_proxy_to_item, empty_proxy_document


def test_empty_proxy_document_returns_v2_schema():
    assert empty_proxy_document(generated_at="2026-05-22T12:00:00Z") == {
        "version": 2,
        "generated_at": "2026-05-22T12:00:00Z",
        "total": 0,
        "items": [],
    }


def test_checked_proxy_to_item_returns_clean_v2_item():
    item = checked_proxy_to_item(
        CheckedProxy(
            endpoint="1.2.3.4:8080",
            source_protocol="http",
            usable_as=("http", "https"),
            exit_ip="8.8.8.8",
            country_code="US",
            anonymous=True,
            score=90.8,
            success_rate=1.0,
            checks_passed=2,
            checks_failed=0,
            avg_latency_ms=420,
            last_error=None,
            checked_at="2026-05-22T12:00:00Z",
        )
    )

    assert item["endpoint"] == "1.2.3.4:8080"
    assert item["source_protocol"] == "http"
    assert item["usable_as"] == ["http", "https"]
    assert item["quality"]["score"] == 90.8
    assert item["network"]["anonymous"] is True
    assert item["timestamps"]["checked_at"] == "2026-05-22T12:00:00Z"
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest tests/test_storage.py tests/test_config.py -v`

Expected: FAIL because v2 helpers do not exist.

- [ ] **Step 4: Implement v2 models**

Replace model JSON helpers in `proxy_pool/models.py` with v2 names while keeping `ProxyCandidate` and `Protocol`:

```python
Protocol = Literal["http", "socks4", "socks5"]
Capability = Literal["http", "https"]


@dataclass(slots=True)
class CheckedProxy:
    endpoint: str
    source_protocol: Protocol
    usable_as: tuple[Capability, ...]
    exit_ip: str
    country_code: str
    anonymous: bool
    score: float
    success_rate: float
    checks_passed: int
    checks_failed: int
    avg_latency_ms: int
    last_error: str | None
    checked_at: str
```

Define `ProxyItem`, `ProxyDocument`, `empty_proxy_document(generated_at: str = "")`, and `checked_proxy_to_item(proxy: CheckedProxy)`. Clamp score to `0..100`, success rate to `0..1`, counts to nonnegative ints, and latency to nonnegative int.

- [ ] **Step 5: Implement v2 storage**

In `proxy_pool/storage.py`, expose:

```python
def read_proxy_document(path: Path) -> ProxyDocument: ...
def write_proxy_document(path: Path, payload: ProxyDocument) -> None: ...
```

Rules:
- missing/malformed/non-dict/non-v2 returns `empty_proxy_document()`;
- valid v2 normalizes `items` to valid v2 proxy items;
- recompute `total = len(items)`;
- write atomically using same temp/flush/fsync/replace behavior.

Keep old function names as aliases only if needed by intermediate tests, but update project code in later tasks.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_storage.py tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add proxy_pool/models.py proxy_pool/storage.py tests/test_storage.py tests/test_config.py
git commit -m "feat: introduce v2 proxy document model"
```

## Task 2: Checker Emits V2 Items

**Files:**
- Modify: `proxy_pool/checker.py`
- Test: `tests/test_checker.py`

- [ ] **Step 1: Update checker tests to v2 model**

Update checker tests so `aggregate_attempts()` returns `CheckedProxy` with:

```python
assert proxy.endpoint == "1.2.3.4:80"
assert proxy.source_protocol == "http"
assert proxy.usable_as == ("http", "https")
assert proxy.exit_ip == "8.8.8.8"
assert proxy.country_code == "US"
assert proxy.anonymous is True
assert proxy.checks_passed == 2
assert proxy.checks_failed == 1
assert proxy.success_rate == 2 / 3
assert proxy.avg_latency_ms == 300
assert proxy.last_error == "timeout"
```

Replace `build_proxy_json` tests with `build_proxy_document`:

```python
def test_build_proxy_document_returns_v2_shape():
    result = build_proxy_document(
        [
            CheckedProxy(
                endpoint="1.2.3.4:80",
                source_protocol="http",
                usable_as=("http",),
                exit_ip="8.8.8.8",
                country_code="US",
                anonymous=True,
                score=50.0,
                success_rate=1.0,
                checks_passed=1,
                checks_failed=0,
                avg_latency_ms=500,
                last_error=None,
                checked_at="2026-05-22T12:00:00Z",
            )
        ],
        generated_at="2026-05-22T12:00:00Z",
    )

    assert result["version"] == 2
    assert result["total"] == 1
    assert result["items"][0]["source_protocol"] == "http"
```

- [ ] **Step 2: Run checker tests to verify failure**

Run: `uv run pytest tests/test_checker.py -v`

Expected: FAIL because checker still emits old model fields.

- [ ] **Step 3: Refactor checker aggregation**

In `proxy_pool/checker.py`:

- `aggregate_attempts(...)` takes `source_protocol: Protocol`.
- Build `usable_as` from successful capabilities.
- Pick `exit_ip` as first successful observed IP.
- Convert average timeout seconds to `avg_latency_ms = int(round(avg_timeout_seconds * 1000))`.
- Return v2 `CheckedProxy`.

- [ ] **Step 4: Replace document builder and pipeline write**

Replace grouped `build_proxy_json` with:

```python
def build_proxy_document(proxies: Iterable[CheckedProxy], generated_at: str) -> ProxyDocument:
    items = [checked_proxy_to_item(proxy) for proxy in proxies]
    return {"version": 2, "generated_at": generated_at, "total": len(items), "items": items}
```

Update `run_pipeline()` to:

- collect all checked proxies into one list;
- sort them by score/latency;
- write with `write_proxy_document(settings.result_path, payload)`;
- return `ProxyDocument`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_checker.py -v`

Expected: PASS.

- [ ] **Step 6: Run full tests and fix dependent tests**

Run: `uv run pytest -v`

Expected: failures in API/app/storage tests that still expect v1. Do not fix all API here unless required to keep full suite green for commit; if fixing, keep scope to names/imports only. Before commit, full suite must pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add proxy_pool/checker.py tests/test_checker.py
git commit -m "feat: emit v2 proxy documents from checker"
```

## Task 3: V2 API And Stats

**Files:**
- Modify: `proxy_pool/api.py`
- Test: `tests/test_api.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Replace API tests with v2 response tests**

Update `tests/test_api.py` to use `write_proxy_document()` and assert:

- `GET /proxies` returns `{total, items}`;
- `GET /` returns same shape;
- filters `source_protocol`, `usable_as`, `min_score`, `min_success_rate`, `country`, `anonymous`, `limit` work;
- non-finite `min_score` and `min_success_rate` return 422;
- `GET /stats` returns protocol and capability counts.

Include this representative test:

```python
def test_proxies_filters_v2_fields(tmp_path: Path):
    path = tmp_path / "proxies.json"
    write_proxy_document(path, {
        "version": 2,
        "generated_at": "2026-05-22T12:00:00Z",
        "total": 2,
        "items": [
            make_proxy_item("1.1.1.1:80", source_protocol="http", usable_as=["http", "https"], score=90.0, success_rate=1.0, country="US", anonymous=True),
            make_proxy_item("2.2.2.2:1080", source_protocol="socks5", usable_as=["http"], score=40.0, success_rate=0.5, country="DE", anonymous=False),
        ],
    })
    client = TestClient(create_app(result_path=path, start_scheduler=False))

    response = client.get("/proxies?source_protocol=http&usable_as=https&min_score=80&min_success_rate=0.9&country=us&anonymous=true&limit=10")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["endpoint"] == "1.1.1.1:80"
```

- [ ] **Step 2: Run API tests to verify failure**

Run: `uv run pytest tests/test_api.py -v`

Expected: FAIL because v2 API routes are not implemented.

- [ ] **Step 3: Implement v2 API**

In `proxy_pool/api.py`:

- `GET /proxies` returns v2 document with filtered/sorted/limited items.
- `GET /` calls same handler or returns same v2 shape.
- `GET /stats` computes `total`, `by_source_protocol`, `by_capability`, and `last_refresh` from storage document and app state.
- Keep `GET /health`.

Filter semantics:

- `source_protocol` exact case-insensitive;
- `usable_as` membership;
- `min_score` finite;
- `min_success_rate` finite;
- `country` compares `network.country_code` case-insensitive;
- `anonymous` string boolean;
- `limit` positive int capped at 1000.

- [ ] **Step 4: Run API tests**

Run: `uv run pytest tests/test_api.py tests/test_app.py -v`

Expected: PASS.

- [ ] **Step 5: Run full tests**

Run: `uv run pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add proxy_pool/api.py tests/test_api.py tests/test_app.py
git commit -m "feat: expose clean v2 proxy api"
```

## Task 4: Scheduler Refresh Metadata

**Files:**
- Modify: `proxy_pool/scheduler.py`
- Modify: `proxy_pool/app.py`
- Modify: `proxy_pool/api.py`
- Test: `tests/test_app.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Add refresh metadata tests**

Add tests asserting scheduler/app state tracks:

- `last_refresh.started_at`;
- `last_refresh.finished_at`;
- `last_refresh.duration_seconds`;
- `last_refresh.proxies_alive`.

Use monkeypatched `run_pipeline()` returning a v2 document with `total=2`.

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_app.py tests/test_api.py -v`

Expected: FAIL because refresh metadata is not tracked.

- [ ] **Step 3: Implement metadata tracking**

In `proxy_pool/scheduler.py`, add optional callbacks:

```python
async def scheduler_loop(settings, stop_event, on_error=None, on_success=None):
    started = datetime.now(UTC)
    payload = await run_pipeline(settings)
    finished = datetime.now(UTC)
    if on_success:
        on_success(started, finished, payload)
```

In `proxy_pool/app.py`, store `app.state.last_refresh` dict.

In `/stats`, include `last_refresh` from app state, otherwise zero/null values.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_app.py tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add proxy_pool/scheduler.py proxy_pool/app.py proxy_pool/api.py tests/test_app.py tests/test_api.py
git commit -m "feat: track refresh statistics"
```

## Task 5: Documentation And Roadmap V2 Cleanup

**Files:**
- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `docs/architecture.md`
- Modify: `docs/configuration.md`
- Modify: `docs/operations.md`
- Modify: `.planning/ROADMAP.md`

- [ ] **Step 1: Update docs to v2 only**

Remove normal-output references to:

- `countryCode`;
- `is_anonymous`;
- `timeout`;
- `total_count_of_proxies`;
- top-level `http`, `socks4`, `socks5` buckets.

Document:

- `GET /proxies`;
- `GET /` same shape;
- `GET /stats`;
- v2 item fields;
- v2 filters;
- v2 storage shape;
- source protocol vs usable capability.

- [ ] **Step 2: Update roadmap**

Mark clean v2 API/storage as complete in `.planning/ROADMAP.md` and add future work only for long-term history/source reputation/CI live smoke.

- [ ] **Step 3: Run tests**

Run: `uv run pytest -v`

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add README.md docs/api.md docs/architecture.md docs/configuration.md docs/operations.md .planning/ROADMAP.md
git commit -m "docs: document clean v2 proxy api"
```

## Task 6: Final Verification And Live Smoke

**Files:**
- All changed files.

- [ ] **Step 1: Run full tests**

Run: `uv run pytest -v`

Expected: all tests PASS.

- [ ] **Step 2: Compile**

Run: `uv run python -m compileall proxy_pool tests`

Expected: exits 0.

- [ ] **Step 3: Import app**

Run: `uv run python -c "from proxy_pool.app import app; print(app.title)"`

Expected: `Proxy Pool`.

- [ ] **Step 4: Docker build**

Run: `docker build -t proxy-pool:local .`

Expected: image builds.

- [ ] **Step 5: Bounded live smoke**

Run a Docker one-off script that:

- fetches up to 300 candidates from one known source;
- checks them with one HTTP endpoint and bounded concurrency;
- prints v2 items if any live proxies are found;
- exits successfully if v2 code runs and either writes an empty v2 document or finds live proxies.

Expected: no crash, v2 shape produced. Nonzero live yield is useful evidence but not required because public proxies are unstable.

- [ ] **Step 6: Final status**

Run: `git status --short`

Expected: clean.

## Self-Review

- Spec coverage: v2 model, storage, API, stats, checker output, scheduler metadata, docs, tests, Docker, and live smoke are covered.
- Red-flag scan: no unresolved marker text or unspecified implementation steps remain.
- Type consistency: `CheckedProxy`, `ProxyItem`, `ProxyDocument`, `empty_proxy_document`, `checked_proxy_to_item`, `read_proxy_document`, `write_proxy_document`, `build_proxy_document`, `/proxies`, and `/stats` are named consistently.
