# Proxy Pool

Proxy Pool is a public proxy scraper, checker, and API service. It reads proxy source URLs from `config.ini`, extracts proxy candidates, checks whether each proxy can reach an external IP API, records country and anonymity metadata, and serves the current working proxy list through a FastAPI application.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management and commands
- Docker and Docker Compose are optional for containerized operation

## Install

```sh
uv sync --extra dev
```

## Run Locally

Start the API service with the background refresh scheduler:

```sh
uv run uvicorn proxy_pool.app:app --host 0.0.0.0 --port 5000
```

Run one scrape/check cycle without starting the API service:

```sh
uv run proxy-pool-scrape
```

By default, the included `config.ini` writes JSON output to `/app/data/proxies.json`. For local runs, change `[General] SavePath` to a writable local directory or leave it empty to write beside `config.ini`.

## Docker

Build and run the container:

```sh
docker build -t proxy-pool .
docker run --rm -p 5000:5000 -v proxy-pool-data:/app/data proxy-pool
```

Or use Compose:

```sh
docker compose up --build
```

The Docker image runs as the non-root `proxypool` user and persists results in the `/app/data` volume.

## API Summary

- `GET /` returns the full proxy JSON document when no filters are supplied.
- `GET /` with filters returns a flattened list of matching proxy rows.
- Supported filters are `prototypes`, `countrycodes`, `isanonymous`, `maxtimeout`, `minscore`, `supportshttps`, and `minsuccessrate`.
- `GET /health` returns service health, storage path/existence, and scheduler fields.

## Documentation

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [API](docs/api.md)
- [Operations](docs/operations.md)

## License

MIT License
