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

### Phase 2: Checker Correctness

**Status:** Complete.

**Problem:** Checker results depended on a single public IP API and shared protocol handling. That created rate-limit risk and could hide protocol-specific failures.

**Completed scope:**

- Added configurable `[Checker]` endpoints with defaults for multiple public IP APIs.
- Added repeated HTTP and HTTPS capability attempts per candidate.
- Defined response parsing for `query`, `origin`, or `ip` plus optional country metadata.
- Aggregated attempt results into success rate, counts, usable capability support, average latency, latest error, and checked timestamp.
- Added score-based quality sorting and v2 API filters, including rejection of non-finite numeric filters.
- Added deterministic tests for checker helpers, endpoint planning, protocol connector construction, failure handling, quality JSON compatibility, and API quality filters.

**Acceptance checks:**

- Checker tests verify anonymous versus transparent proxy classification.
- Checker tests verify each protocol uses the correct proxy URL scheme.
- Timeout, malformed JSON, missing-field, and request failure cases return no checked proxy without aborting the pipeline.
- Configuration documents the selected check endpoints and expected response shape.

### Phase 3: Clean V2 API And Storage

**Status:** Complete.

**Problem:** The modernization branch temporarily carried legacy grouped JSON fields and filters. The service needed one clean v2 API/storage contract that represents source protocol, usable capabilities, quality, network identity, and refresh statistics without legacy response shapes.

**Completed scope:**

- Replaced storage with the v2 proxy document schema: `version`, `generated_at`, `total`, and `items`.
- Added v2 proxy items with `endpoint`, `source_protocol`, `usable_as`, `quality`, `network`, and `timestamps`.
- Updated the checker pipeline to write v2 documents directly.
- Exposed `GET /proxies` and `GET /` with the same v2 list shape.
- Added v2 filters for `source_protocol`, `usable_as`, `min_score`, `min_success_rate`, `country`, `anonymous`, and `limit`.
- Added `GET /stats` with totals by source protocol, totals by usable capability, and last refresh metadata.
- Updated documentation to describe v2 as the normal output.

**Acceptance checks:**

- `uv run pytest -v` passes.
- API and storage documentation describe v2 only as the normal contract.
- Operators can distinguish the protocol used to connect to a proxy from the destination capabilities that succeeded through it.

### Remaining Future Work

- Track long-term per-proxy quality history across refreshes if persistent trend data becomes necessary.
- Add source reputation metrics so operators can identify source URLs that consistently provide high-quality or low-quality candidates.
- Add CI live smoke automation that tolerates variable public proxy yield while proving the scrape/check/write loop still produces v2 output.
