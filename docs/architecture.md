# Architecture

Proxy Pool is a small asynchronous Python service with a scrape/check pipeline, JSON file storage, and a FastAPI read API.

## Components

- `proxy_pool.config` loads `config.ini` into immutable `Settings`.
- `proxy_pool.sources` fetches configured source URLs and extracts `ip:port` proxy candidates.
- `proxy_pool.checker` tests candidates through `aiohttp-socks`, records source protocol, usable capabilities, and quality metrics, scores results, and builds the v2 result JSON.
- `proxy_pool.storage` reads and writes the v2 result JSON file. Writes are atomic through a temporary file and replace.
- `proxy_pool.scheduler` runs the pipeline repeatedly inside the API process.
- `proxy_pool.api` exposes `GET /proxies` and `GET /` for proxy data, `GET /stats` for aggregates, and `GET /health` for status.
- `proxy_pool.app` creates the FastAPI app, starts/stops the scheduler during lifespan, and provides the `proxy-pool` entry point.

## Data Flow

1. `load_config()` reads `[General]`, `[Checker]`, and enabled `[HTTP]`, `[SOCKS4]`, and `[SOCKS5]` source lists.
2. `collect_candidates()` downloads each enabled source and extracts unique proxy candidates per protocol.
3. `run_pipeline()` checks candidates concurrently, bounded by `MaxConnections`.
4. For each candidate, `build_attempt_plan()` expands `[Checker]` endpoints into repeated HTTP and HTTPS attempts based on `AttemptsPerProxy`, `CheckHttp`, and `CheckHttps`.
5. Each attempt connects through the candidate proxy with the candidate source protocol, calls a matching public IP endpoint, and parses an observed exit IP plus optional country metadata.
6. `aggregate_attempts()` counts successes and failures, rejects proxies below `RequiredSuccesses` or `MinSuccessRate`, derives HTTP/HTTPS usable capabilities, averages successful latency, records the latest failed-attempt error, and classifies anonymity by comparing observed IPs with the candidate IP.
7. `calculate_score()` produces a `0.0` to `100.0` score from success rate, HTTPS support, anonymity, and average latency.
8. Each successful proxy is converted to a v2 item with endpoint, source protocol, usable capabilities, quality, network, and timestamp sections.
9. Results are sorted by score, average latency, and endpoint when `SortBySpeed = yes`; otherwise they are sorted by endpoint.
10. `write_proxy_document()` writes the result document to `SavePath / JsonResultFilename`.
11. `GET /proxies` and `GET /` read the current file on each request and return the v2 list shape, optionally filtered.

## Runtime Modes

- API service: `proxy_pool.app:app` starts FastAPI and a background scheduler when `config.ini` is available.
- One-off refresh: `proxy-pool-scrape` runs the pipeline once and exits.
- Docker: the image starts Uvicorn, runs as non-root user `proxypool`, and stores data under `/app/data`.

## Storage Model

The JSON schema is:

```json
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 1,
  "items": [
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

Proxy items contain these fields:

| Field | Description |
| --- | --- |
| `endpoint` | Proxy endpoint as `ip:port`. |
| `source_protocol` | Protocol used to connect to the proxy candidate: `http`, `socks4`, or `socks5`. |
| `usable_as` | Destination capabilities that passed checks through this proxy: `http`, `https`, or both. |
| `quality.score` | Quality score from `0.0` to `100.0`. |
| `quality.success_rate` | Successful attempts divided by total attempts. |
| `quality.checks_passed` | Number of successful attempts. |
| `quality.checks_failed` | Number of failed attempts. |
| `quality.avg_latency_ms` | Average successful attempt latency in milliseconds. |
| `quality.last_error` | Most recent failed-attempt error, or `null`. |
| `network.exit_ip` | IP address observed by a successful check endpoint. |
| `network.country_code` | Country code reported by a successful check endpoint, or an empty string. |
| `network.anonymous` | Whether any successful attempt observed an IP different from the candidate IP. |
| `timestamps.checked_at` | UTC timestamp for the check cycle. |

If the result file is missing, invalid JSON, or has unexpected structure, API reads fall back to the empty schema instead of failing the request.

`source_protocol` identifies how Proxy Pool connects to the proxy itself. `usable_as` identifies which destination types worked through that proxy during checking.
