# Clean Proxy Pool v2 Design

Date: 2026-05-22

## Goal

Refactor Proxy Pool into a clean v2 service that returns a stable, high-quality list of verified proxies with clear protocol/capability metadata. Backward compatibility with the legacy grouped JSON shape is not a priority.

The service should make it obvious:

- how a proxy is reached (`source_protocol`);
- what traffic it can actually carry (`usable_as`);
- how reliable and fast it is (`quality`);
- what network identity it exposes (`network`).

## Design Direction

This is a breaking v2 API and storage redesign.

Remove the legacy primary response shape:

```json
{
  "total_count_of_proxies": 0,
  "http": [],
  "socks4": [],
  "socks5": []
}
```

Replace it with a single normalized list of verified proxy endpoints.

## Proxy Model

Each verified proxy item has this shape:

```json
{
  "endpoint": "1.2.3.4:8080",
  "source_protocol": "http",
  "usable_as": ["http", "https"],
  "quality": {
    "score": 91.2,
    "success_rate": 1.0,
    "checks_passed": 4,
    "checks_failed": 0,
    "avg_latency_ms": 420,
    "last_error": null
  },
  "network": {
    "exit_ip": "8.8.8.8",
    "country_code": "US",
    "anonymous": true
  },
  "timestamps": {
    "checked_at": "2026-05-22T12:00:00Z"
  }
}
```

Field semantics:

- `endpoint`: proxy host and port in `ip:port` format.
- `source_protocol`: protocol used to connect to the proxy: `http`, `socks4`, or `socks5`.
- `usable_as`: traffic capabilities verified through this proxy. Values are `http` and/or `https`.
- `quality.score`: `0..100`, higher is better.
- `quality.success_rate`: successful checks divided by total checks.
- `quality.checks_passed`: number of successful check attempts.
- `quality.checks_failed`: number of failed check attempts.
- `quality.avg_latency_ms`: average latency in milliseconds across successful attempts.
- `quality.last_error`: latest failed check error, or `null`.
- `network.exit_ip`: observed outbound IP returned by check endpoints.
- `network.country_code`: country code if available.
- `network.anonymous`: whether the observed outbound IP differs from the proxy endpoint IP.
- `timestamps.checked_at`: UTC timestamp for the check cycle.

## Protocol And Capability Semantics

`source_protocol` describes how the proxy itself is reached:

- `http`: HTTP proxy.
- `socks4`: SOCKS4 proxy.
- `socks5`: SOCKS5 proxy.

`usable_as` describes verified traffic capability:

- `http`: an HTTP endpoint was successfully reached through the proxy.
- `https`: an HTTPS endpoint was successfully reached through the proxy.

For HTTP proxies, `usable_as = ["https"]` means HTTPS CONNECT works.

For SOCKS proxies, `usable_as = ["http", "https"]` means HTTP/HTTPS destinations work through the SOCKS connector.

## Storage Schema

Replace `proxies.json` contents with v2 storage:

```json
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 123,
  "items": []
}
```

Storage remains atomic: write a temporary file in the same directory, flush/fsync, and replace.

Storage readers should return an empty v2 document if the file is missing, malformed, or not version 2.

The service does not need to normalize old v1 stored data. Operators can delete old `proxies.json` or let the next refresh replace it.

## API

### `GET /proxies`

Primary endpoint. Always returns the same shape:

```json
{
  "total": 123,
  "items": []
}
```

Supported filters:

- `source_protocol`: one of `http`, `socks4`, `socks5`.
- `usable_as`: one of `http`, `https`.
- `min_score`: finite float.
- `min_success_rate`: finite float.
- `country`: country code, case-insensitive.
- `anonymous`: boolean.
- `limit`: positive integer, bounded by a configured or hard-coded maximum.

Filters combine with AND semantics.

Default sort:

```text
quality.score desc, quality.avg_latency_ms asc, endpoint asc
```

Invalid numeric filters such as `nan`, `inf`, and `-inf` return HTTP 422.

### `GET /stats`

Returns operational summary:

```json
{
  "total": 123,
  "by_source_protocol": {
    "http": 80,
    "socks4": 20,
    "socks5": 23
  },
  "by_capability": {
    "http": 100,
    "https": 72
  },
  "last_refresh": {
    "started_at": "2026-05-22T12:00:00Z",
    "finished_at": "2026-05-22T12:00:42Z",
    "duration_seconds": 42,
    "sources_checked": 40,
    "candidates_found": 10000,
    "proxies_alive": 123
  }
}
```

If refresh metadata is not available yet, `last_refresh` fields may be `null` or zeroed consistently.

### `GET /health`

Keep health endpoint for service/scheduler/storage state.

It should continue to include:

- `status`
- `storage_path`
- `storage_exists`
- `scheduler_running`
- `last_scheduler_error`

It may also include `total` and latest refresh timestamps if cheap to read.

### Root Endpoint

`GET /` should either redirect to `/proxies` or return the same v2 response as `/proxies`. Prefer returning the same response to keep simple curl usage ergonomic.

## Checker Pipeline

The refresh pipeline becomes:

1. Load source URLs by source protocol.
2. Fetch sources and parse `ip:port` candidates.
3. De-duplicate by `(endpoint, source_protocol)`.
4. Build check attempts from configured endpoints and enabled capabilities.
5. Run attempts under an attempt-level concurrency limit.
6. Aggregate attempts into v2 proxy items.
7. Score and sort items.
8. Write v2 storage atomically.

The checker should keep the current multi-endpoint quality logic but output the v2 model directly rather than compatibility-oriented `CheckedProxy` fields.

## Configuration

Keep `config.ini` for now.

The existing source sections remain:

- `[HTTP]`
- `[SOCKS4]`
- `[SOCKS5]`

The `[Checker]` section remains and controls:

- endpoints;
- attempts per proxy;
- required successes;
- HTTP/HTTPS capability checks;
- minimum success rate.

Optional future cleanup may rename settings, but this phase should avoid changing source configuration format unless needed.

## Removed Or Deprioritized Legacy Concepts

Remove these as primary API/storage concepts:

- `countryCode`
- `is_anonymous`
- `timeout`
- `total_count_of_proxies`
- top-level `http`, `socks4`, `socks5` buckets
- query behavior where unfiltered and filtered responses have different shapes

The same information is represented with better names:

- `network.country_code`
- `network.anonymous`
- `quality.avg_latency_ms`
- `total`
- `items`
- `source_protocol`

## Documentation

Update:

- `README.md`
- `docs/api.md`
- `docs/architecture.md`
- `docs/configuration.md`
- `docs/operations.md`
- `.planning/ROADMAP.md`

Docs should describe v2 only, not present legacy fields as normal output.

## Testing

Required test coverage:

- v2 storage empty/malformed/version handling.
- v2 storage atomic write/read.
- v2 model serialization.
- checker aggregation into v2 proxy items.
- `/proxies` response shape is always `{total, items}`.
- `/proxies` filters: `source_protocol`, `usable_as`, `min_score`, `min_success_rate`, `country`, `anonymous`, `limit`.
- `/proxies` rejects non-finite numeric filters.
- `/stats` counts source protocols and capabilities correctly.
- `/` returns the v2 proxy response.
- scheduler still writes v2 storage.
- Docker build still succeeds.

Add a bounded live smoke check when network is available. The live check should not require a nonzero yield from a fixed small sample because public proxies are unstable, but it should prove the command runs and v2 JSON shape is produced. A larger optional smoke can assert at least one live proxy when the network/source produces one.

## Non-Goals

- Backward compatibility with v1 JSON consumers.
- Database-backed long-term proxy history.
- Authentication.
- Web UI.
- Guaranteeing public proxy availability.

## Acceptance Criteria

- `GET /proxies` and `GET /` return v2 `{total, items}` shape.
- Proxy items clearly identify source protocol and usable capabilities.
- Legacy primary fields are removed from normal API output.
- Checker writes v2 storage atomically.
- API filters and stats operate on v2 fields.
- Tests pass with `uv run pytest`.
- Docker image builds.
- Documentation describes v2 behavior accurately.
