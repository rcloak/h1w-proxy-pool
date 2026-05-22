# Proxy Pool Project

## Purpose

Proxy Pool is a public proxy scraper, checker, and read API. It collects proxy candidates from configured source URLs, validates working HTTP, SOCKS4, and SOCKS5 proxies, records country and anonymity metadata, stores the current result set as JSON, and serves proxy data through a small web service.

## Current Modernization Goal

The current branch modernizes the original proxy-pool implementation into a maintainable Python service with:

- `uv` dependency and command management.
- A packaged `proxy_pool` module with typed configuration, source collection, checker, storage, scheduler, and API components.
- FastAPI served by Uvicorn instead of the legacy Flask-only web process.
- Docker and Docker Compose support with persistent `/app/data` storage and a non-root runtime user.
- Unit tests covering configuration, storage, source parsing, checker behavior, API responses, and app lifecycle basics.
- User-facing documentation for architecture, configuration, API usage, and operations.

Tasks 1-9 have completed the first modernization pass on this branch. The remaining project work should harden correctness, freshness, and operations rather than reintroduce broad rewrites.

## Constraints

- Keep the service small and dependency-light; avoid adding infrastructure unless it directly addresses a known risk.
- Preserve the checked-in `config.ini` source-list model so operators can enable, disable, or replace sources without code changes.
- Continue supporting HTTP, SOCKS4, and SOCKS5 proxy categories in the JSON output and API filters.
- Treat `/app/data/proxies.json` as the Docker persistence path while allowing local development to use a writable configured path.
- Use asynchronous network I/O and bounded concurrency for scraping and checking so slow public endpoints do not stall the whole service.
- Keep tests deterministic by mocking network behavior instead of depending on live public proxy sources or check endpoints.

## Known Risks

- Source lists may be stale, unavailable, duplicated, or contain endpoints that no longer publish parseable `ip:port` rows.
- Checker correctness currently depends on one public, rate-limited IP API endpoint, which can throttle, fail, or bias results.
- Protocol checks use a shared response interpretation path; protocol-specific connection behavior needs targeted validation.
- Public proxy validation is inherently flaky because candidate proxies, upstream source pages, and external IP APIs change constantly.
- Test coverage exists but should be expanded around failure modes, scheduler behavior, API filtering combinations, and Docker/operations assumptions.
- Health and logging are functional but minimal; production troubleshooting needs clearer refresh metrics and error visibility.
