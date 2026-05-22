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

## One-Off Refresh

Run a single scrape/check cycle and exit:

```sh
uv run proxy-pool-scrape
```

This uses the same `config.ini` settings as the API service and writes to `SavePath / JsonResultFilename`.

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

## Troubleshooting

If `GET /` returns an empty proxy document:

- Check `GET /health` and confirm `storage_path` is expected.
- Confirm `storage_exists` is `true`; the first refresh may still be running.
- Run `uv run proxy-pool-scrape` once and watch for errors.
- Check that source sections are enabled and have URLs.
- Lower `MaxConnections` if the host is resource constrained.

If the scheduler is not running:

- Start the app through `proxy_pool.app:app` or `proxy-pool` so the lifespan handler runs.
- Confirm `config.ini` exists in the working directory used to start the service.
- Inspect `last_scheduler_error` for the most recent refresh failure.

If Docker cannot write results:

- Confirm the container is using `/app/data` as `SavePath`.
- Use the provided image or Compose file so `/app/data` is owned by the non-root `proxypool` user.
- Verify the volume mount is writable.
