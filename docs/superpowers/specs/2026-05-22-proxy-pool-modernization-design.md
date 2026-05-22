# Proxy Pool Modernization Design

Date: 2026-05-22

## Goal

Modernize the legacy proxy-pool project into a maintainable service managed by UV, served by Uvicorn, runnable in Docker, documented, and governed by GSD planning artifacts.

The work should preserve the useful behavior of the existing project while creating a foundation for fixing stale sources, improving proxy liveness checks, and operating the service reliably.

## Current State

The project currently consists of a small flat Python codebase:

- `scrap_proxies.py` scrapes proxy source URLs, validates candidates, and writes output.
- `web_server.py` serves JSON through Flask and starts the scraper in a background thread via subprocess.
- `config.ini` stores runtime settings and source URLs.
- `requirements.txt` pins old dependencies.
- `Dockerfile` runs `web_server.py` directly with Python.

Known issues include stale proxy source URLs, fragile filtering in the API, direct JSON writes while the web server may read the same file, use of `shell=True`, no tests, old dependencies, and no structured planning/documentation.

## Chosen Approach

Use the larger refactor path:

- Convert the codebase into a proper Python package.
- Replace Flask/Waitress with FastAPI served by Uvicorn.
- Move dependency management from `requirements.txt` to UV with `pyproject.toml` and `uv.lock`.
- Update Docker to install and run through UV.
- Keep `config.ini` as the initial runtime configuration format to avoid changing operational behavior and config syntax at the same time.
- Preserve the existing output JSON schema for compatibility.
- Add documentation and GSD planning artifacts for the migration and follow-up work.

## Package Structure

The target package structure is:

- `proxy_pool/app.py`: ASGI application factory and app instance.
- `proxy_pool/api.py`: HTTP routes and query filtering.
- `proxy_pool/config.py`: typed configuration loading from `config.ini`.
- `proxy_pool/sources.py`: source fetching and `ip:port` extraction.
- `proxy_pool/checker.py`: proxy validation logic and concurrency control.
- `proxy_pool/storage.py`: atomic JSON read/write helpers.
- `proxy_pool/scheduler.py`: background periodic scraping/checking task.
- `proxy_pool/models.py`: shared result and proxy data structures if needed.
- `tests/`: unit tests for config, parsing, filtering, and storage.

Legacy entry points may remain temporarily as thin compatibility wrappers if they reduce migration risk, but core behavior should live in the package.

## API Design

The service will expose:

- `GET /`: return the full proxy JSON if no filters are provided, or return a filtered list when filters are provided.
- `GET /health`: return service health and basic storage status.

Supported filters on `GET /` remain:

- `prototypes`: comma-separated protocol list, e.g. `http,socks5`.
- `countrycodes`: comma-separated country code list.
- `isanonymous`: boolean-like value.
- `maxtimeout`: maximum proxy timeout in seconds.

The filter behavior must be safe when any parameter is omitted. `maxtimeout` must only be parsed when present.

## Scraping And Checking Design

The scraper/checker pipeline will be split into clear steps:

1. Load enabled protocol sources from configuration.
2. Fetch all sources with bounded timeouts and a browser-like user agent.
3. Extract proxy candidates with the existing `ip:port` regex or an equivalent tested implementation.
4. De-duplicate candidates per protocol.
5. Check candidates with a semaphore-limited async checker.
6. Sort results by speed or natural address order based on configuration.
7. Persist the final JSON atomically.

Source fetch failures should be recorded/logged but must not stop the whole run.

Proxy check failures should remove only the failed candidate.

The first implementation can preserve the existing check endpoint behavior, but the plans must include follow-up work to improve HTTP/HTTPS/SOCKS-specific validation and reduce dependency on a single rate-limited service.

## Storage Design

`proxies.json` will be written atomically:

1. Write complete JSON to a temporary file in the same directory.
2. Flush and close the temporary file.
3. Replace the target file with `Path.replace()`.

API reads should handle missing files and malformed/incomplete data gracefully.

The JSON schema remains:

```json
{
  "total_count_of_proxies": 0,
  "http": [],
  "socks4": [],
  "socks5": []
}
```

Each proxy item keeps the current fields:

- `address`
- `countryCode`
- `is_anonymous`
- `timeout`

## Runtime And Scheduling

The ASGI app will start a background scheduler on application startup. The scheduler will run the scrape/check pipeline immediately, then repeat at a configurable interval.

The legacy subprocess loop in `web_server.py` should be removed. The service should not call itself through shell commands.

Default runtime behavior should match the current effective behavior where practical:

- Listen on port `5000` in Docker.
- Save data under `/app` in Docker unless overridden.
- Run the refresh periodically.

## UV And Docker Design

Add UV-managed project files:

- `pyproject.toml`
- `uv.lock`

Runtime dependencies should include FastAPI, Uvicorn, aiohttp, aiohttp-socks, rich, and uvloop where appropriate.

Dev dependencies should include pytest and pytest-asyncio.

Docker should:

- Use a slim Python base image.
- Install UV.
- Copy project metadata and lockfile first for dependency caching.
- Run `uv sync --frozen`.
- Start with `uv run uvicorn proxy_pool.app:app --host 0.0.0.0 --port 5000`.

Add `docker-compose.yml` if useful for local operation with a data volume.

## GSD Planning

Initialize GSD planning artifacts for the project. The initial roadmap should include phases for:

1. Project modernization foundation: UV, FastAPI/Uvicorn, Docker, package layout.
2. Proxy source cleanup: remove dead sources, document source health, add source validation workflow.
3. Checker correctness: protocol-specific checks, better timeout/rate-limit behavior, fallback check endpoints.
4. Test coverage: parser, config, API filters, storage, scheduler boundaries.
5. Operations: logging, health/status details, runtime configuration, monitoring-oriented output.

## Documentation

Create or update:

- `README.md`: quick start with UV and Docker.
- `docs/architecture.md`: package responsibilities and data flow.
- `docs/configuration.md`: `config.ini` fields and runtime paths.
- `docs/api.md`: endpoints, parameters, examples.
- `docs/operations.md`: Docker, refresh interval, data file, troubleshooting.
- GSD roadmap/plans for all known follow-up work.

## Testing And Verification

Minimum verification for the modernization:

- `uv sync --frozen` succeeds.
- `uv run pytest` passes.
- `uv run python -m compileall proxy_pool tests` succeeds.
- `uv run uvicorn proxy_pool.app:app --host 127.0.0.1 --port 5000` can import the app.
- Docker image builds.

Network-heavy scraping should not be required for every unit test. Network behavior should be isolated behind functions that can be tested with mocked responses or small deterministic fixtures.

## Non-Goals For First Implementation

- Replacing `config.ini` with TOML/YAML.
- Building a UI.
- Guaranteeing high-quality public proxies from free sources.
- Adding authentication.
- Adding a database.

## Risks

- Free proxy sources are unstable and can disappear without notice.
- The current IP geolocation/check service is rate-limited.
- Large concurrent checks can exhaust file descriptors or trigger remote throttling.
- Docker path behavior must be handled carefully to avoid breaking current `/app/proxies.json` expectations.

## Acceptance Criteria

The modernization is acceptable when:

- The service is UV-managed and no longer depends on `requirements.txt` as the source of truth.
- The ASGI service runs under Uvicorn locally and in Docker.
- The API preserves the existing JSON result shape and filter intent.
- The scraper/checker pipeline is package-based rather than shelling out from the web server.
- JSON writes are atomic.
- Documentation explains installation, configuration, API usage, Docker usage, and operational behavior.
- GSD planning artifacts exist and cover the known repair and enhancement work.
- Basic automated tests pass.
