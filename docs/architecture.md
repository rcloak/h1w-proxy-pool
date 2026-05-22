# Architecture

Proxy Pool is a small asynchronous Python service with a scrape/check pipeline, JSON file storage, and a FastAPI read API.

## Components

- `proxy_pool.config` loads `config.ini` into immutable `Settings`.
- `proxy_pool.sources` fetches configured source URLs and extracts `ip:port` proxy candidates.
- `proxy_pool.checker` tests candidates through `aiohttp-socks`, records country, anonymity, and response time, and builds the result JSON.
- `proxy_pool.storage` reads and writes the result JSON file. Writes are atomic through a temporary file and replace.
- `proxy_pool.scheduler` runs the pipeline repeatedly inside the API process.
- `proxy_pool.api` exposes `GET /` for proxy data and `GET /health` for status.
- `proxy_pool.app` creates the FastAPI app, starts/stops the scheduler during lifespan, and provides the `proxy-pool` entry point.

## Data Flow

1. `load_config()` reads `[General]` settings and enabled `[HTTP]`, `[SOCKS4]`, and `[SOCKS5]` source lists.
2. `collect_candidates()` downloads each enabled source and extracts unique proxy candidates per protocol.
3. `run_pipeline()` checks candidates concurrently, bounded by `MaxConnections`.
4. Each successful proxy is converted to JSON with `address`, `countryCode`, `is_anonymous`, and `timeout`.
5. Results are sorted by speed when `SortBySpeed = yes`; otherwise they are sorted by address.
6. `write_proxy_json()` writes the result document to `SavePath / JsonResultFilename`.
7. `GET /` reads the current file on each request and returns either the full JSON document or a filtered flattened list.

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

If the result file is missing, invalid JSON, or has unexpected structure, API reads fall back to the empty schema instead of failing the request.
