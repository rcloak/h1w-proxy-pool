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

**Status:** Complete.

**Problem:** Checker results depended on a single public IP API and shared protocol handling. That created rate-limit risk and could hide protocol-specific failures.

**Completed scope:**

- Added configurable `[Checker]` endpoints with defaults for multiple public IP APIs.
- Added repeated HTTP and HTTPS capability attempts per candidate.
- Defined response parsing for `query`, `origin`, or `ip` plus optional `countryCode`.
- Aggregated attempt results into success rate, counts, protocol support, average timeout, latest error, and checked timestamp.
- Added score-based quality sorting and API filters for `minscore`, `supportshttps`, and `minsuccessrate`, including rejection of non-finite numeric filters.
- Added deterministic tests for checker helpers, endpoint planning, protocol connector construction, failure handling, quality JSON compatibility, and API quality filters.

**Acceptance checks:**

- Checker tests verify anonymous versus transparent proxy classification.
- Checker tests verify each protocol uses the correct proxy URL scheme.
- Timeout, malformed JSON, missing-field, and request failure cases return no checked proxy without aborting the pipeline.
- Configuration documents the selected check endpoints and expected response shape.

**Future follow-up:**

- Track long-term per-proxy quality history across refreshes if persistent trend data becomes necessary.
- Add source reputation metrics so operators can identify source URLs that consistently provide high-quality or low-quality candidates.

### Phase 4: Test Coverage

**Status:** Planned.

**Problem:** The first modernization pass already covers scheduler refresh/error tracking, health reporting for scheduler errors, malformed and atomic storage behavior, API filter interactions, and deterministic checker quality behavior. Remaining gaps are concentrated around source freshness audit findings, dependency cleanup, live smoke automation, and CI/runtime smoke coverage.

**Actions:**

- Add tests for any source parsing or config edge cases discovered during the source cleanup phase, without duplicating the existing extraction tests.
- Add coverage for cleanup of transitional Flask/Waitress dependencies if they are removed, including import and entry-point checks that prove FastAPI/Uvicorn remains the active runtime path.
- Add Docker or command-level smoke checks where feasible in CI or local verification docs, especially for `uv run proxy-pool-scrape`, `uv run uvicorn proxy_pool.app:app`, and image startup assumptions.
- Add live smoke automation that tolerates variable public proxy yield while still proving the scrape/check/write loop completes.
- Track coverage by behavior rather than chasing a numeric threshold alone.

**Acceptance checks:**

- `uv run pytest` passes without live network dependency.
- New tests fail deterministically when source audit assumptions or runtime dependency cleanup regress.
- CI or documented smoke checks cover Docker image startup and one-off refresh execution where environment support is available.
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
