# Architecture

Proxy Pool is a small asynchronous Python service with a scrape/check pipeline, JSON file storage, and a FastAPI read API.

## Components

- `proxy_pool.config` loads `config.ini` into immutable `Settings`.
- `proxy_pool.sources` fetches configured source URLs and extracts `ip:port` proxy candidates.
- `proxy_pool.checker` tests candidates through `aiohttp-socks`, records protocol capabilities and quality metrics, scores results, and builds the result JSON.
- `proxy_pool.storage` reads and writes the result JSON file. Writes are atomic through a temporary file and replace.
- `proxy_pool.scheduler` runs the pipeline repeatedly inside the API process.
- `proxy_pool.api` exposes `GET /` for proxy data and `GET /health` for status.
- `proxy_pool.app` creates the FastAPI app, starts/stops the scheduler during lifespan, and provides the `proxy-pool` entry point.

## Data Flow

1. `load_config()` reads `[General]`, `[Checker]`, and enabled `[HTTP]`, `[SOCKS4]`, and `[SOCKS5]` source lists.
2. `collect_candidates()` downloads each enabled source and extracts unique proxy candidates per protocol.
3. `run_pipeline()` checks candidates concurrently, bounded by `MaxConnections`.
4. For each candidate, `build_attempt_plan()` expands `[Checker]` endpoints into repeated HTTP and HTTPS attempts based on `AttemptsPerProxy`, `CheckHttp`, and `CheckHttps`.
5. Each attempt connects through the candidate proxy with the candidate protocol, calls a matching public IP endpoint, and parses one of `query`, `origin`, or `ip` plus optional `countryCode`.
6. `aggregate_attempts()` counts successes and failures, rejects proxies below `RequiredSuccesses` or `MinSuccessRate`, derives HTTP/HTTPS support, averages successful timeouts, records the latest failed-attempt error, and classifies anonymity by comparing observed IPs with the candidate IP.
7. `calculate_score()` produces a `0.0` to `100.0` score from success rate, HTTPS support, anonymity, and average timeout.
8. Each successful proxy is converted to JSON with `address`, `countryCode`, `is_anonymous`, `timeout`, `score`, `success_rate`, `success_count`, `failure_count`, `supports_http`, `supports_https`, `avg_timeout`, `last_error`, and `checked_at`.
9. Results are sorted by score, average timeout, and address when `SortBySpeed = yes`; otherwise they are sorted by address.
10. `write_proxy_json()` writes the result document to `SavePath / JsonResultFilename`.
11. `GET /` reads the current file on each request and returns either the full JSON document or a filtered flattened list.

## Runtime Modes

- API service: `proxy_pool.app:app` starts FastAPI and a background scheduler when `config.ini` is available.
- One-off refresh: `proxy-pool-scrape` runs the pipeline once and exits.
- Docker: the image starts Uvicorn, runs as non-root user `proxypool`, and stores data under `/app/data`.

## Storage Model

The JSON schema is:

```json
{
  "total_count_of_proxies": 0,
  "http": [],
  "socks4": [],
  "socks5": []
}
```

Proxy items contain these fields:

| Field | Description |
| --- | --- |
| `address` | Proxy address as `ip:port`. |
| `countryCode` | Country code reported by a successful check endpoint, or an empty string. |
| `is_anonymous` | Whether any successful attempt observed an IP different from the candidate IP. |
| `timeout` | Average successful attempt timeout in seconds. |
| `score` | Quality score from `0.0` to `100.0`. |
| `success_rate` | Successful attempts divided by total attempts. |
| `success_count` | Number of successful attempts. |
| `failure_count` | Number of failed attempts. |
| `supports_http` | Whether an HTTP endpoint attempt succeeded. |
| `supports_https` | Whether an HTTPS endpoint attempt succeeded. |
| `avg_timeout` | Average successful attempt timeout in seconds. |
| `last_error` | Most recent failed-attempt error, or `null`. |
| `checked_at` | UTC timestamp for the check cycle. |

If the result file is missing, invalid JSON, or has unexpected structure, API reads fall back to the empty schema instead of failing the request.
