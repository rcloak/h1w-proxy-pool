# Operations

## Local Service

Install dependencies:

```sh
uv sync --extra dev
```

Start the API service and background scheduler:

```sh
uv run uvicorn proxy_pool.app:app --host 0.0.0.0 --port 5000
```

The scheduler runs one scrape/check cycle, writes the result JSON, waits `RefreshIntervalSeconds`, and repeats until the service stops.

For local development, make sure `[General] SavePath` points to a writable directory. Leaving `SavePath` empty writes `JsonResultFilename` next to `config.ini`.

Live checker results depend on the configured `[Checker]` endpoints and on public proxy behavior at the time of the run. Endpoint rate limits, blocked public IP APIs, transparent proxies, unstable proxy nodes, and regional network failures can all change proxy yield without a code or configuration change.

Common local API calls:

```sh
curl http://localhost:5000/health
curl http://localhost:5000/proxies
curl 'http://localhost:5000/proxies?usable_as=https&min_score=80&limit=20'
curl http://localhost:5000/stats
```

## One-Off Refresh

Run a single scrape/check cycle and exit:

```sh
uv run proxy-pool-scrape
```

This uses the same `config.ini` settings as the API service and writes to `SavePath / JsonResultFilename`.

After it finishes, start the API or inspect the JSON file directly. The file shape includes storage metadata:

```json
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 0,
  "items": []
}
```

## Docker

Build and run directly:

```sh
docker build -t proxy-pool .
docker run --rm -p 5000:5000 -v proxy-pool-data:/app/data proxy-pool
```

Run with Compose:

```sh
docker compose up --build
```

The image:

- Uses Python 3.12.
- Starts Uvicorn on `0.0.0.0:5000`.
- Runs as the non-root `proxypool` user.
- Stores data in `/app/data`, mounted by Compose as the `proxy-pool-data` named volume.

## Data File Path

The effective result path is:

```text
SavePath / JsonResultFilename
```

With the checked-in Docker-oriented config, this is:

```text
/app/data/proxies.json
```

For local runs outside Docker, either create and grant access to `/app/data`, change `SavePath` to a local directory, or leave `SavePath` empty.

## Health Checks

Check the service:

```sh
curl http://localhost:5000/health
```

Useful fields:

- `storage_path` shows where the API is reading data from.
- `storage_exists` tells whether a result file has been written yet.
- `scheduler_running` tells whether the background scheduler task is active.
- `last_scheduler_error` contains the last recorded scheduler failure message, or `null`.

FastAPI's generated docs are available at `http://localhost:5000/docs` when the service is running.

## Troubleshooting

If `GET /` returns an empty proxy document:

- Check `GET /health` and confirm `storage_path` is expected.
- Confirm `storage_exists` is `true`; the first refresh may still be running.
- Check `GET /stats` for `total`, protocol counts, capability counts, and `last_refresh` metadata.
- Run `uv run proxy-pool-scrape` once and watch for errors.
- Check that source sections are enabled and have URLs.
- Check that `[Checker] Endpoints` are reachable from the host and are not rate-limiting requests.
- Check whether public proxies are failing the configured `RequiredSuccesses` or `MinSuccessRate` thresholds.
- Lower `MaxConnections` if the host is resource constrained.
- Remember that public proxy lists are noisy; an empty verified pool can be a real live-check result.

The result file should be a v2 document with `version`, `generated_at`, `total`, and `items`. Each item records `endpoint`, `source_protocol`, `usable_as`, `quality`, `network`, and `timestamps`.

During a long refresh, inspect progress with:

```sh
curl http://localhost:5000/stats
```

`current_refresh.elapsed_seconds`, `current_refresh.progress_percent`, and `current_refresh.checked` should increase as batches complete. `GET /proxies` reads the latest verified result file, so its `total` can grow before the refresh finishes and before `current_refresh.status` returns to `idle`.

`dead_cache` in `GET /stats` shows how many recently failed proxies are being skipped. `currently_skipped` should grow after failed checks are recorded and shrink as TTLs expire. The SQLite file is stored at `/app/data/proxy_state.sqlite3` with the Docker config.

If the scheduler is not running:

- Start the app through `proxy_pool.app:app` or `proxy-pool` so the lifespan handler runs.
- Confirm `config.ini` exists in the working directory used to start the service.
- Inspect `last_scheduler_error` for the most recent refresh failure.

If Docker cannot write results:

- Confirm the container is using `/app/data` as `SavePath`.
- Use the provided image or Compose file so `/app/data` is owned by the non-root `proxypool` user.
- Verify the volume mount is writable.
