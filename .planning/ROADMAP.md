# Proxy Pool Roadmap

## Milestone 1: Modernization And Hardening

Goal: turn the legacy proxy scraper into a maintainable FastAPI service, then address the highest-risk correctness and operations gaps found during modernization review.

### Phase 1: UV, FastAPI, Uvicorn, Docker

**Status:** Complete on the modernization branch through Tasks 1-9.

**Outcome:** Replace ad hoc execution with a packaged Python project managed by `uv`, expose the API through FastAPI/Uvicorn, and provide Dockerized runtime support.

**Completed scope:**

- Added `pyproject.toml`, `uv.lock`, and package entry points for service and one-off scrape execution.
- Introduced `proxy_pool.app`, `proxy_pool.api`, and scheduler startup through FastAPI lifespan handling.
- Added Dockerfile and Compose support with `/app/data` persistence and a non-root runtime user.
- Documented installation, local execution, Docker usage, API behavior, configuration, architecture, and operations.

**Acceptance checks:**

- `uv sync --extra dev` installs runtime and test dependencies.
- `uv run uvicorn proxy_pool.app:app --host 0.0.0.0 --port 5000` starts the API service.
- `uv run proxy-pool-scrape` runs one scrape/check/write cycle.
- `docker build -t proxy-pool .` builds the container image.

### Phase 2: Source Cleanup

**Status:** Planned.

**Problem:** The configured proxy sources are the first reliability bottleneck. Stale or duplicated source URLs reduce yield, slow refreshes, and make checker failures harder to diagnose.

**Actions:**

- Audit every enabled `[HTTP]`, `[SOCKS4]`, and `[SOCKS5]` source in `config.ini` for reachability, freshness, and parseable proxy output.
- Remove dead, duplicate, parked, or consistently empty sources.
- Group or comment replacement candidates in `config.ini` so operators know which sources are expected to be maintained.
- Add deterministic tests for source extraction edge cases discovered during the audit.
- Document how to validate and rotate source URLs without changing code.

**Acceptance checks:**

- Source audit notes identify removed and retained URLs by protocol.
- `collect_candidates()` still deduplicates candidates per protocol after source updates.
- Tests cover representative valid rows, invalid ports, duplicate rows, and noisy source text.

### Phase 3: Checker Correctness

**Status:** Planned.

**Problem:** Checker results depend on a single public IP API and shared protocol handling. That creates rate-limit risk and can hide protocol-specific failures.

**Actions:**

- Add a configurable check endpoint instead of hard-coding only `http://ip-api.com/json/?fields=8219`.
- Define the required check response contract for query IP and country code fields.
- Add protocol-specific checker tests for HTTP, SOCKS4, and SOCKS5 connector URL construction and failure handling.
- Handle check endpoint throttling, malformed JSON, missing fields, and timeout errors explicitly in tests.
- Consider lightweight fallback endpoint support only if it can be tested without live network calls.

**Acceptance checks:**

- Checker tests verify anonymous versus transparent proxy classification.
- Checker tests verify each protocol uses the correct proxy URL scheme.
- Timeout, throttling, malformed JSON, and missing-field cases return no checked proxy without aborting the pipeline.
- Configuration documents the selected check endpoint and expected response shape.

### Phase 4: Test Coverage

**Status:** Planned.

**Problem:** The first modernization pass already covers scheduler refresh/error tracking, health reporting for scheduler errors, malformed and atomic storage behavior, and API filter interactions. Remaining gaps are concentrated around source freshness audit findings, checker endpoint behavior, protocol-specific connector behavior, dependency cleanup, and operational smoke coverage.

**Actions:**

- Add tests for any source parsing or config edge cases discovered during the source cleanup phase, without duplicating the existing extraction tests.
- Add checker tests for configurable endpoint behavior, check response contract validation, throttled responses, malformed JSON, missing fields, and protocol-specific connector URL construction.
- Add coverage for cleanup of transitional Flask/Waitress dependencies if they are removed, including import and entry-point checks that prove FastAPI/Uvicorn remains the active runtime path.
- Add Docker or command-level smoke checks where feasible in CI or local verification docs, especially for `uv run proxy-pool-scrape`, `uv run uvicorn proxy_pool.app:app`, and image startup assumptions.
- Track coverage by behavior rather than chasing a numeric threshold alone.

**Acceptance checks:**

- `uv run pytest` passes without live network dependency.
- New tests fail deterministically when source audit assumptions, checker endpoint parsing, protocol connector construction, or runtime dependency cleanup regress.
- Documentation lists the primary local verification commands for contributors.

### Phase 5: Operations

**Status:** Planned.

**Problem:** Operators need clearer runtime visibility than a basic health endpoint and swallowed scrape/check exceptions provide.

**Actions:**

- Expand `/health` with last refresh start, last refresh finish, last success, last failure, and proxy count if available.
- Add structured logging for source fetch failures, checker failures by class, scheduler refresh summaries, and storage writes.
- Ensure logs avoid dumping full proxy lists or excessive noisy per-candidate output by default.
- Document recommended local, Docker, and Compose troubleshooting flows.
- Add operational tests for health payload fields and scheduler error visibility.

**Acceptance checks:**

- `/health` provides enough information to tell whether the service is running, refreshing, failing, or waiting between refreshes.
- Logs identify source and checker failure categories without exposing unnecessary data volume.
- Operations documentation maps common symptoms to commands and likely causes.
