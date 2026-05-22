# Proxy Pool

Proxy Pool is a Docker-ready public proxy scraper, live checker, and FastAPI service.

It reads public proxy source lists from `config.ini`, extracts `ip:port` candidates, verifies them through real HTTP/HTTPS check endpoints, scores the working proxies, writes a v2 JSON document, and serves the current verified pool through a small API.

## What You Get

- Scraping from configured `HTTP`, `SOCKS4`, and `SOCKS5` source lists.
- Live validation through `aiohttp-socks`, not just source-list parsing.
- Clean v2 API responses with stable fields: `endpoint`, `source_protocol`, `usable_as`, `quality`, `network`, and `timestamps`.
- API filters for protocol, capability, score, success rate, country, anonymity, and limit.
- Background refresh scheduler when the API service is running.
- Atomic JSON writes so the API does not serve partially-written files.
- Docker image that runs as a non-root user and persists data in `/app/data`.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for local dependency management and commands
- Docker and Docker Compose for containerized operation

## Quick Start With Docker

Build and run:

```sh
docker build -t proxy-pool .
docker run --rm -p 5000:5000 -v proxy-pool-data:/app/data proxy-pool
```

Or use Compose:

```sh
docker compose up --build
```

The service listens on `http://localhost:5000`. The first refresh starts when the API process starts. Public proxies are unstable, so the first useful result may take time and can be empty if the current source lists produce no working proxies.

Check service health:

```sh
curl http://localhost:5000/health
```

Get verified proxies:

```sh
curl http://localhost:5000/proxies
```

Get only HTTPS-capable HTTP proxies with strong quality:

```sh
curl 'http://localhost:5000/proxies?source_protocol=http&usable_as=https&min_score=80&min_success_rate=0.9&limit=20'
```

## Local Development

Install dependencies:

```sh
uv sync --extra dev
```

Important local config note: the checked-in `config.ini` is Docker-oriented and writes to `/app/data/proxies.json`. For local runs, either create `/app/data`, change `[General] SavePath` to a writable local directory, or leave `SavePath` empty to write next to `config.ini`.

Start the API service with the background scheduler:

```sh
uv run uvicorn proxy_pool.app:app --host 0.0.0.0 --port 5000
```

Run one scrape/check cycle without starting the API:

```sh
uv run proxy-pool-scrape
```

Run tests:

```sh
uv run pytest -v
```

## API Summary

During a long refresh, `GET /proxies` continues to return the latest partial verified result file. Use `GET /stats` and its `current_refresh` object to watch `checked`, `total`, and `alive` counts advance as batches complete.

### `GET /proxies`

Returns the current verified proxy list:

```json
{
  "total": 1,
  "items": [
    {
      "endpoint": "1.2.3.4:8080",
      "source_protocol": "http",
      "usable_as": ["http", "https"],
      "quality": {
        "score": 90.8,
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
  ]
}
```

The API response intentionally does not expose the storage-only `version` and `generated_at` fields. The on-disk JSON file includes them; API list responses return only `{ "total", "items" }`.

### `GET /`

Same response shape and filters as `GET /proxies`.

### `GET /stats`

Returns aggregate counts and refresh metadata:

```json
{
  "total": 1,
  "by_source_protocol": {
    "http": 1,
    "socks4": 0,
    "socks5": 0
  },
  "by_capability": {
    "http": 1,
    "https": 1
  },
  "last_refresh": {
    "started_at": "2026-05-22T12:00:00+00:00",
    "finished_at": "2026-05-22T12:00:05+00:00",
    "duration_seconds": 5.0,
    "proxies_alive": 1
  },
  "current_refresh": {
    "status": "running",
    "started_at": "2026-05-22T12:05:00+00:00",
    "finished_at": null,
    "checked": 120,
    "total": 500,
    "alive": 18,
    "current_protocol": "http"
  }
}
```

### `GET /health`

Returns service, storage, and scheduler state:

```json
{
  "status": "ok",
  "storage_path": "/app/data/proxies.json",
  "storage_exists": true,
  "scheduler_running": true,
  "last_scheduler_error": null,
  "refresh_running": true
}
```

## Filters

`GET /` and `GET /proxies` support these query parameters:

| Parameter | Example | Meaning |
| --- | --- | --- |
| `source_protocol` | `http`, `socks4`, `socks5` | How Proxy Pool connects to the proxy itself. |
| `usable_as` | `http`, `https` | Destination capability that passed live checks through the proxy. |
| `min_score` | `80` | Minimum `quality.score`, from `0.0` to `100.0`. |
| `min_success_rate` | `0.9` | Minimum `quality.success_rate`, from `0.0` to `1.0`. |
| `country` | `US` | Match `network.country_code`, case-insensitive. |
| `anonymous` | `true`, `false` | Match `network.anonymous`. |
| `limit` | `20` | Maximum returned items. Must be positive; capped at `1000`. |

Filters are combined with AND semantics. Results are sorted by `quality.score` descending, `quality.avg_latency_ms` ascending, then `endpoint` ascending.

## Field Meaning

- `endpoint`: proxy address as strict `ip:port`.
- `source_protocol`: protocol used to connect to that proxy candidate: `http`, `socks4`, or `socks5`.
- `usable_as`: destination protocols that worked during checks: `http`, `https`, or both.
- `quality.score`: score from `0.0` to `100.0`, based on success rate, HTTPS support, anonymity, and latency.
- `quality.success_rate`: successful attempts divided by all attempts for that proxy.
- `quality.checks_passed` / `quality.checks_failed`: live check counts.
- `quality.avg_latency_ms`: average latency across successful attempts.
- `quality.last_error`: latest failed attempt error, or `null`.
- `network.exit_ip`: IP observed by the check endpoint through the proxy.
- `network.country_code`: country code returned by the check endpoint, or an empty string.
- `network.anonymous`: `true` if the observed exit IP differs from the proxy candidate IP.
- `timestamps.checked_at`: UTC timestamp for the check cycle.

## Configuration

Main settings live in `config.ini`:

- `[General] Timeout`: per-request proxy check timeout in seconds.
- `[General] MaxConnections`: maximum concurrent proxy checks.
- `[General] SavePath` and `JsonResultFilename`: output file path.
- `[General] RefreshIntervalSeconds`: scheduler interval while the API runs.
- `[HTTP]`, `[SOCKS4]`, `[SOCKS5]`: enabled source URLs grouped by source protocol.
- `[Checker] Endpoints`: external IP APIs used to verify proxies.
- `[Checker] AttemptsPerProxy`, `RequiredSuccesses`, `CheckHttp`, `CheckHttps`, `MinSuccessRate`: quality-check policy.

See [Configuration](docs/configuration.md) for every field.

## More Documentation

- [API](docs/api.md)
- [Configuration](docs/configuration.md)
- [Operations](docs/operations.md)
- [Architecture](docs/architecture.md)

## License

MIT License
