# Quality Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade proxy validation from a single liveness check to a multi-endpoint quality checker with repeated attempts, protocol capabilities, scoring, and quality API filters.

**Architecture:** Extend the existing package without adding a database. Add checker configuration to `proxy_pool.config`, expand proxy models/storage compatibility, refactor `proxy_pool.checker` around pure parsing/aggregation/scoring helpers plus async network execution, then expose quality fields through storage and API filters.

**Tech Stack:** Python 3.12+, UV, FastAPI, aiohttp, aiohttp-socks, pytest, Docker.

---

## File Map

- Modify `config.ini`: add `[Checker]` defaults.
- Modify `proxy_pool/config.py`: add `CheckerSettings` and load `[Checker]` with safe fallbacks.
- Modify `proxy_pool/models.py`: extend `CheckedProxy` and `ProxyJsonItem` with quality fields.
- Modify `proxy_pool/storage.py`: accept old items and validate/normalize new quality fields.
- Modify `proxy_pool/checker.py`: add endpoint parsing, attempt aggregation, scoring, capability checks, and quality sorting.
- Modify `proxy_pool/api.py`: add `minscore`, `supportshttps`, and `minsuccessrate` filters.
- Modify docs: `docs/configuration.md`, `docs/api.md`, `docs/architecture.md`, `docs/operations.md`, `.planning/ROADMAP.md`.
- Modify tests: `tests/test_config.py`, `tests/test_checker.py`, `tests/test_storage.py`, `tests/test_api.py`.

## Task 1: Checker Configuration

**Files:**
- Modify: `config.ini`
- Modify: `proxy_pool/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add failing config tests**

Append to `tests/test_config.py`:

```python
def test_load_config_reads_checker_settings(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
SavePath =

[Folders]

[HTTP]
Enabled = no
Sources =

[SOCKS4]
Enabled = no
Sources =

[SOCKS5]
Enabled = no
Sources =

[Checker]
Endpoints =
    http://example.test/ip
    https://example.test/ip
AttemptsPerProxy = 3
RequiredSuccesses = 2
CheckHttp = no
CheckHttps = yes
MinSuccessRate = 0.75
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.checker.endpoints == ("http://example.test/ip", "https://example.test/ip")
    assert settings.checker.attempts_per_proxy == 3
    assert settings.checker.required_successes == 2
    assert settings.checker.check_http is False
    assert settings.checker.check_https is True
    assert settings.checker.min_success_rate == 0.75


def test_load_config_uses_checker_defaults_when_section_missing(tmp_path: Path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
[General]
SavePath =

[Folders]

[HTTP]
Enabled = no
Sources =

[SOCKS4]
Enabled = no
Sources =

[SOCKS5]
Enabled = no
Sources =
""".strip(),
        encoding="utf-8",
    )

    settings = load_config(config_file)

    assert settings.checker.endpoints == (
        "http://httpbin.org/ip",
        "https://api.ipify.org?format=json",
        "http://ip-api.com/json/?fields=8219",
    )
    assert settings.checker.attempts_per_proxy == 2
    assert settings.checker.required_successes == 1
    assert settings.checker.check_http is True
    assert settings.checker.check_https is True
    assert settings.checker.min_success_rate == 0.5
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_config.py -v`

Expected: FAIL because `Settings` has no `checker` field.

- [ ] **Step 3: Implement checker config**

In `proxy_pool/config.py`, add:

```python
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
```

Add `checker: CheckerSettings` to `Settings`.

Add helper:

```python
def _load_checker_settings(parser: ConfigParser) -> CheckerSettings:
    if parser.has_section("Checker"):
        section = parser["Checker"]
        endpoints = tuple(line.strip() for line in section.get("Endpoints", "").splitlines() if line.strip())
        if not endpoints:
            endpoints = DEFAULT_CHECK_ENDPOINTS
        return CheckerSettings(
            endpoints=endpoints,
            attempts_per_proxy=max(1, section.getint("AttemptsPerProxy", fallback=2)),
            required_successes=max(1, section.getint("RequiredSuccesses", fallback=1)),
            check_http=section.getboolean("CheckHttp", fallback=True),
            check_https=section.getboolean("CheckHttps", fallback=True),
            min_success_rate=min(1.0, max(0.0, section.getfloat("MinSuccessRate", fallback=0.5))),
        )
    return CheckerSettings(
        endpoints=DEFAULT_CHECK_ENDPOINTS,
        attempts_per_proxy=2,
        required_successes=1,
        check_http=True,
        check_https=True,
        min_success_rate=0.5,
    )
```

Call it from `load_config()`.

- [ ] **Step 4: Add checked-in config defaults**

Append to `config.ini`:

```ini

[Checker]
Endpoints =
    http://httpbin.org/ip
    https://api.ipify.org?format=json
    http://ip-api.com/json/?fields=8219
AttemptsPerProxy = 2
RequiredSuccesses = 1
CheckHttp = yes
CheckHttps = yes
MinSuccessRate = 0.5
```

- [ ] **Step 5: Run config tests**

Run: `uv run pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add config.ini proxy_pool/config.py tests/test_config.py
git commit -m "feat: add checker quality configuration"
```

## Task 2: Quality Models And Storage Compatibility

**Files:**
- Modify: `proxy_pool/models.py`
- Modify: `proxy_pool/storage.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add failing model/storage tests**

Append to `tests/test_storage.py`:

```python
def test_read_proxy_json_preserves_quality_fields(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        '{"http": [{"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": true, "timeout": 0.5, "score": 90.0, "success_rate": 1.0, "success_count": 4, "failure_count": 0, "supports_http": true, "supports_https": true, "avg_timeout": 0.5, "last_error": null, "checked_at": "2026-05-22T12:00:00Z"}], "socks4": [], "socks5": []}',
        encoding="utf-8",
    )

    result = read_proxy_json(target)

    item = result["http"][0]
    assert item["score"] == 90.0
    assert item["success_rate"] == 1.0
    assert item["success_count"] == 4
    assert item["failure_count"] == 0
    assert item["supports_http"] is True
    assert item["supports_https"] is True
    assert item["avg_timeout"] == 0.5
    assert item["last_error"] is None
    assert item["checked_at"] == "2026-05-22T12:00:00Z"


def test_read_proxy_json_accepts_legacy_items_without_quality_fields(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        '{"http": [{"address": "1.2.3.4:80", "countryCode": "US", "is_anonymous": true, "timeout": 0.5}], "socks4": [], "socks5": []}',
        encoding="utf-8",
    )

    result = read_proxy_json(target)

    assert result["total_count_of_proxies"] == 1
    assert result["http"][0]["address"] == "1.2.3.4:80"
```

Append to `tests/test_config.py`:

```python
def test_checked_proxy_to_json_includes_quality_fields():
    from proxy_pool.models import CheckedProxy, checked_proxy_to_json

    item = checked_proxy_to_json(
        CheckedProxy(
            address="1.2.3.4:80",
            country_code="US",
            is_anonymous=True,
            timeout=0.5,
            score=90.0,
            success_rate=1.0,
            success_count=4,
            failure_count=0,
            supports_http=True,
            supports_https=True,
            avg_timeout=0.5,
            last_error=None,
            checked_at="2026-05-22T12:00:00Z",
        )
    )

    assert item["score"] == 90.0
    assert item["supports_https"] is True
    assert item["checked_at"] == "2026-05-22T12:00:00Z"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_storage.py tests/test_config.py -v`

Expected: FAIL because quality fields are missing from model/storage normalization.

- [ ] **Step 3: Extend model types**

In `proxy_pool/models.py`, extend `CheckedProxy` fields after `timeout`:

```python
    score: float = 0.0
    success_rate: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    supports_http: bool = False
    supports_https: bool = False
    avg_timeout: float = 0.0
    last_error: str | None = None
    checked_at: str = ""
```

Extend `ProxyJsonItem` with the same quality fields.

Update `checked_proxy_to_json()` to include all quality fields.

- [ ] **Step 4: Extend storage validation**

In `proxy_pool/storage.py`, keep existing required legacy validation. Optional quality fields are normalized as:

```python
score = _number(item.get("score"), 0.0)
success_rate = _number(item.get("success_rate"), 0.0)
success_count = _int(item.get("success_count"), 0)
failure_count = _int(item.get("failure_count"), 0)
supports_http = item.get("supports_http") if isinstance(item.get("supports_http"), bool) else False
supports_https = item.get("supports_https") if isinstance(item.get("supports_https"), bool) else False
avg_timeout = _number(item.get("avg_timeout"), timeout)
last_error = item.get("last_error") if isinstance(item.get("last_error"), str) or item.get("last_error") is None else str(item.get("last_error"))
checked_at = item.get("checked_at") if isinstance(item.get("checked_at"), str) else ""
```

Add small private helpers `_number()` and `_int()`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_storage.py tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add proxy_pool/models.py proxy_pool/storage.py tests/test_storage.py tests/test_config.py
git commit -m "feat: add proxy quality fields"
```

## Task 3: Pure Checker Quality Helpers

**Files:**
- Modify: `proxy_pool/checker.py`
- Test: `tests/test_checker.py`

- [ ] **Step 1: Add failing helper tests**

Append to `tests/test_checker.py`:

```python
from proxy_pool.checker import (
    CheckAttempt,
    aggregate_attempts,
    calculate_score,
    extract_observed_ip,
)


def test_extract_observed_ip_supports_common_response_shapes():
    assert extract_observed_ip({"query": "1.2.3.4", "countryCode": "US"}) == ("1.2.3.4", "US")
    assert extract_observed_ip({"origin": "5.6.7.8"}) == ("5.6.7.8", "")
    assert extract_observed_ip({"ip": "9.9.9.9"}) == ("9.9.9.9", "")


def test_extract_observed_ip_rejects_missing_or_invalid_ip():
    assert extract_observed_ip({}) is None
    assert extract_observed_ip({"origin": "not-an-ip"}) is None


def test_calculate_score_clamps_to_zero_to_one_hundred():
    assert calculate_score(success_rate=1.0, supports_https=True, is_anonymous=True, avg_timeout=0.1) == 94.0
    assert calculate_score(success_rate=0.0, supports_https=False, is_anonymous=False, avg_timeout=99.0) == 0.0


def test_aggregate_attempts_builds_quality_proxy():
    attempts = [
        CheckAttempt(success=True, capability="http", observed_ip="8.8.8.8", country_code="US", timeout=0.2, error=None),
        CheckAttempt(success=True, capability="https", observed_ip="8.8.8.8", country_code="US", timeout=0.4, error=None),
        CheckAttempt(success=False, capability="https", observed_ip=None, country_code="", timeout=None, error="timeout"),
    ]

    proxy = aggregate_attempts(
        address="1.2.3.4:80",
        candidate_ip="1.2.3.4",
        attempts=attempts,
        required_successes=1,
        min_success_rate=0.5,
        checked_at="2026-05-22T12:00:00Z",
    )

    assert proxy is not None
    assert proxy.success_count == 2
    assert proxy.failure_count == 1
    assert proxy.success_rate == 2 / 3
    assert proxy.supports_http is True
    assert proxy.supports_https is True
    assert proxy.avg_timeout == 0.3
    assert proxy.timeout == 0.3
    assert proxy.last_error == "timeout"
```

- [ ] **Step 2: Run checker tests to verify failure**

Run: `uv run pytest tests/test_checker.py -v`

Expected: FAIL because helpers do not exist.

- [ ] **Step 3: Implement pure helpers**

In `proxy_pool/checker.py`, add:

```python
from dataclasses import dataclass
from ipaddress import ip_address


@dataclass(frozen=True, slots=True)
class CheckAttempt:
    success: bool
    capability: str
    observed_ip: str | None
    country_code: str
    timeout: float | None
    error: str | None
```

Implement:

```python
def extract_observed_ip(data: Mapping[str, Any]) -> tuple[str, str] | None:
    value = data.get("query") or data.get("origin") or data.get("ip")
    if not isinstance(value, str):
        return None
    observed = value.split(",", 1)[0].strip()
    try:
        ip_address(observed)
    except ValueError:
        return None
    country_code = data.get("countryCode")
    return observed, country_code if isinstance(country_code, str) else ""


def calculate_score(success_rate: float, supports_https: bool, is_anonymous: bool, avg_timeout: float) -> float:
    latency_penalty = min(20.0, max(0.0, avg_timeout * 10.0))
    score = success_rate * 70.0 + (15.0 if supports_https else 0.0) + (10.0 if is_anonymous else 0.0) - latency_penalty
    return round(min(100.0, max(0.0, score)), 2)
```

Implement `aggregate_attempts(...) -> CheckedProxy | None`:

- count successes/failures
- reject if successes < `required_successes`
- reject if success_rate < `min_success_rate`
- reject if no successful timeouts
- country code is first nonempty successful country code or `""`
- `is_anonymous` true if any successful observed IP differs from candidate IP
- supports flags by successful capability
- avg timeout rounded enough for stable test, e.g. `round(..., 6)`
- score from `calculate_score`

- [ ] **Step 4: Run checker tests**

Run: `uv run pytest tests/test_checker.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add proxy_pool/checker.py tests/test_checker.py
git commit -m "feat: add proxy quality scoring helpers"
```

## Task 4: Multi-Endpoint Attempt Execution

**Files:**
- Modify: `proxy_pool/checker.py`
- Test: `tests/test_checker.py`

- [ ] **Step 1: Add failing tests for endpoint selection and attempt building**

Append to `tests/test_checker.py`:

```python
from proxy_pool.config import CheckerSettings
from proxy_pool.models import ProxyCandidate
from proxy_pool.checker import endpoint_supports_capability, build_attempt_plan


def test_endpoint_supports_capability_matches_scheme():
    assert endpoint_supports_capability("http://example.test/ip", "http") is True
    assert endpoint_supports_capability("http://example.test/ip", "https") is False
    assert endpoint_supports_capability("https://example.test/ip", "https") is True


def test_build_attempt_plan_repeats_enabled_capabilities_and_matching_endpoints():
    checker = CheckerSettings(
        endpoints=("http://example.test/ip", "https://example.test/ip"),
        attempts_per_proxy=2,
        required_successes=1,
        check_http=True,
        check_https=True,
        min_success_rate=0.5,
    )

    plan = build_attempt_plan(ProxyCandidate(address="1.2.3.4:80", ip="1.2.3.4"), checker)

    assert [(item.capability, item.endpoint) for item in plan] == [
        ("http", "http://example.test/ip"),
        ("https", "https://example.test/ip"),
        ("http", "http://example.test/ip"),
        ("https", "https://example.test/ip"),
    ]
```

- [ ] **Step 2: Run checker tests to verify failure**

Run: `uv run pytest tests/test_checker.py -v`

Expected: FAIL because attempt plan helpers do not exist.

- [ ] **Step 3: Implement attempt plan helpers**

In `proxy_pool/checker.py`, add:

```python
@dataclass(frozen=True, slots=True)
class PlannedAttempt:
    capability: str
    endpoint: str


def endpoint_supports_capability(endpoint: str, capability: str) -> bool:
    if capability == "http":
        return endpoint.startswith("http://")
    if capability == "https":
        return endpoint.startswith("https://")
    return False


def build_attempt_plan(candidate: ProxyCandidate, checker: CheckerSettings) -> tuple[PlannedAttempt, ...]:
    capabilities: list[str] = []
    if checker.check_http:
        capabilities.append("http")
    if checker.check_https:
        capabilities.append("https")

    attempts: list[PlannedAttempt] = []
    for _ in range(checker.attempts_per_proxy):
        for capability in capabilities:
            for endpoint in checker.endpoints:
                if endpoint_supports_capability(endpoint, capability):
                    attempts.append(PlannedAttempt(capability=capability, endpoint=endpoint))
    return tuple(attempts)
```

- [ ] **Step 4: Refactor async check flow**

Replace the single `CHECK_URL` flow with:

```python
async def run_attempt(candidate: ProxyCandidate, protocol: Protocol, endpoint: str, capability: str, timeout: float) -> CheckAttempt:
    start = perf_counter()
    try:
        connector = ProxyConnector.from_url(f"{protocol}://{candidate.address}")
        async with ClientSession(connector=connector) as session:
            async with session.get(endpoint, timeout=timeout, raise_for_status=True) as response:
                data = await response.json()
        parsed = extract_observed_ip(data)
        if parsed is None:
            return CheckAttempt(False, capability, None, "", None, "missing observed ip")
        observed_ip, country_code = parsed
        return CheckAttempt(True, capability, observed_ip, country_code, perf_counter() - start, None)
    except Exception as exc:
        return CheckAttempt(False, capability, None, "", None, type(exc).__name__)
```

Update `check_candidate(candidate, protocol, timeout, semaphore, checker, checked_at)` to:

- build attempt plan
- execute attempts under semaphore
- aggregate attempts using checker thresholds

Update `run_pipeline()` to pass `settings.checker` and a UTC `checked_at` string.

- [ ] **Step 5: Run checker tests**

Run: `uv run pytest tests/test_checker.py -v`

Expected: PASS.

- [ ] **Step 6: Run full tests**

Run: `uv run pytest -v`

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add proxy_pool/checker.py tests/test_checker.py
git commit -m "feat: run multi-endpoint proxy quality checks"
```

## Task 5: API Quality Filters And Sorting

**Files:**
- Modify: `proxy_pool/api.py`
- Modify: `proxy_pool/checker.py`
- Test: `tests/test_api.py`
- Test: `tests/test_checker.py`

- [ ] **Step 1: Add failing API filter tests**

Append to `tests/test_api.py`:

```python
def test_root_filters_by_quality_fields(tmp_path: Path):
    payload = empty_proxy_json()
    payload["http"] = [
        {"address": "1.1.1.1:80", "countryCode": "US", "is_anonymous": True, "timeout": 0.2, "score": 95.0, "success_rate": 1.0, "success_count": 2, "failure_count": 0, "supports_http": True, "supports_https": True, "avg_timeout": 0.2, "last_error": None, "checked_at": "2026-05-22T12:00:00Z"},
        {"address": "2.2.2.2:80", "countryCode": "US", "is_anonymous": True, "timeout": 0.8, "score": 40.0, "success_rate": 0.5, "success_count": 1, "failure_count": 1, "supports_http": True, "supports_https": False, "avg_timeout": 0.8, "last_error": "timeout", "checked_at": "2026-05-22T12:00:00Z"},
    ]
    payload["total_count_of_proxies"] = 2
    result_path = tmp_path / "proxies.json"
    write_proxy_json(result_path, payload)

    client = TestClient(create_app(result_path=result_path, start_scheduler=False))
    response = client.get("/?minscore=80&supportshttps=true&minsuccessrate=0.9")

    assert response.status_code == 200
    assert [item["address"] for item in response.json()] == ["1.1.1.1:80"]
```

- [ ] **Step 2: Add sorting test**

Append to `tests/test_checker.py`:

```python
def test_sort_checked_prefers_score_then_timeout_then_address():
    proxies = [
        CheckedProxy(address="2.2.2.2:80", country_code="US", is_anonymous=True, timeout=0.1, score=90.0, avg_timeout=0.1),
        CheckedProxy(address="1.1.1.1:80", country_code="US", is_anonymous=True, timeout=0.2, score=95.0, avg_timeout=0.2),
        CheckedProxy(address="3.3.3.3:80", country_code="US", is_anonymous=True, timeout=0.3, score=90.0, avg_timeout=0.3),
    ]

    assert [proxy.address for proxy in sort_checked(proxies, sort_by_speed=True)] == [
        "1.1.1.1:80",
        "2.2.2.2:80",
        "3.3.3.3:80",
    ]
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest tests/test_api.py tests/test_checker.py -v`

Expected: FAIL because filters/sorting are not updated.

- [ ] **Step 4: Implement API filters**

In `proxy_pool/api.py`:

- Add endpoint parameters `minscore: float | None`, `supportshttps: str | None`, `minsuccessrate: float | None`.
- Pass them to `apply_filters`.
- In `apply_filters`, filter conservatively:

```python
if minscore is not None and float(row.get("score", 0.0)) < minscore:
    continue
if minsuccessrate is not None and float(row.get("success_rate", 0.0)) < minsuccessrate:
    continue
if supportshttps is not None and str(row.get("supports_https", False)).lower() != supportshttps.lower():
    continue
```

Ensure "no filters" detection includes the new filters.

- [ ] **Step 5: Implement quality sorting**

In `proxy_pool/checker.py`, update `sort_checked` when `sort_by_speed=True`:

```python
return sorted(proxies, key=lambda proxy: (-proxy.score, proxy.avg_timeout or proxy.timeout, natural_key(proxy.address)))
```

Keep natural sorting when `sort_by_speed=False`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_api.py tests/test_checker.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add proxy_pool/api.py proxy_pool/checker.py tests/test_api.py tests/test_checker.py
git commit -m "feat: add quality filters and sorting"
```

## Task 6: Documentation And Roadmap Updates

**Files:**
- Modify: `docs/configuration.md`
- Modify: `docs/api.md`
- Modify: `docs/architecture.md`
- Modify: `docs/operations.md`
- Modify: `.planning/ROADMAP.md`

- [ ] **Step 1: Update docs**

Update docs to include:

- `[Checker]` config fields and defaults.
- Quality output fields.
- API filters `minscore`, `supportshttps`, `minsuccessrate`.
- Checker data flow: endpoints, attempts, aggregation, score.
- Operations note that live checks depend on external endpoints and public proxy behavior.

- [ ] **Step 2: Update roadmap**

In `.planning/ROADMAP.md`, mark Phase 3 as complete or in progress depending on implementation, and add any remaining follow-up for long-term history/source reputation as future work.

- [ ] **Step 3: Run tests**

Run: `uv run pytest -v`

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/configuration.md docs/api.md docs/architecture.md docs/operations.md .planning/ROADMAP.md
git commit -m "docs: document quality checker"
```

## Task 7: Final Verification

**Files:**
- All changed files.

- [ ] **Step 1: Run tests**

Run: `uv run pytest -v`

Expected: all tests PASS.

- [ ] **Step 2: Compile**

Run: `uv run python -m compileall proxy_pool tests`

Expected: exits 0.

- [ ] **Step 3: App import**

Run: `uv run python -c "from proxy_pool.app import app; print(app.title)"`

Expected: `Proxy Pool`.

- [ ] **Step 4: Docker build**

Run: `docker build -t proxy-pool:local .`

Expected: image builds. If registry/network fails, report exact error.

- [ ] **Step 5: Optional live smoke**

Run a one-off scrape with a small test config and one source if network is available. Expected: command completes and writes JSON. Live yield may vary.

- [ ] **Step 6: Commit final fixes if needed**

If verification requires fixes:

```bash
git add <fixed-files>
git commit -m "fix: complete quality checker"
```

## Self-Review

- Spec coverage: configuration, endpoint parsing, protocol capabilities, metrics, scoring, JSON compatibility, API filters, tests, docs, and verification are covered by tasks.
- Red-flag scan: no unresolved marker text or unspecified implementation steps remain.
- Type consistency: `CheckerSettings`, `CheckedProxy`, `CheckAttempt`, `PlannedAttempt`, `aggregate_attempts`, `calculate_score`, `extract_observed_ip`, and API filter names are introduced before use.
