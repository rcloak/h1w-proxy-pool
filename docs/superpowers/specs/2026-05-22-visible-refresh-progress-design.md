# Visible Refresh Progress Design

## Goal

Make long proxy refreshes observable and useful while they are still running. The API should show partial verified proxies as soon as batches complete instead of staying empty until the entire scrape/check cycle finishes.

## Current Problem

The current `run_pipeline()` flow collects all candidates, checks a whole protocol with one large `asyncio.gather()`, and writes `/app/data/proxies.json` only after the full pipeline finishes. With the current public sources this produced roughly `82,669` candidates and about `496,014` live attempts in one refresh. The API process remains healthy, but `storage_exists` stays `false`, `/proxies` returns no items, and `/stats` cannot show useful progress until the full cycle completes.

## Chosen Approach

Use batch-based partial result writes.

The checker will process candidates in bounded batches. After each batch finishes, it will merge newly verified proxies into the in-memory result set, sort them using the existing output ordering, atomically write the current v2 proxy document, and notify the scheduler/app state about refresh progress.

This keeps the existing file-based architecture and avoids adding a database, queue, or separate worker system.

## API Behavior

`GET /proxies` and `GET /` keep the same response shape:

```json
{
  "total": 123,
  "items": []
}
```

During a refresh, these endpoints read the partial v2 document already written to disk. Results may grow or change ordering as later batches add better proxies. The shape remains stable.

`GET /stats` keeps existing fields and adds `current_refresh`:

```json
{
  "total": 123,
  "by_source_protocol": {
    "http": 80,
    "socks4": 20,
    "socks5": 23
  },
  "by_capability": {
    "http": 123,
    "https": 45
  },
  "last_refresh": {
    "started_at": null,
    "finished_at": null,
    "duration_seconds": null,
    "proxies_alive": 0
  },
  "current_refresh": {
    "status": "running",
    "started_at": "2026-05-22T12:00:00+00:00",
    "finished_at": null,
    "checked": 1500,
    "total": 82669,
    "alive": 123,
    "current_protocol": "http"
  }
}
```

When no refresh is running, `current_refresh.status` is `idle`. After a successful refresh completes, `last_refresh` records the finished refresh and `current_refresh` becomes idle. If a refresh fails, `current_refresh.status` becomes `failed` and includes the last known counts until the next refresh starts.

`GET /health` adds a minimal operator signal:

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

## Checker Changes

`run_pipeline()` will accept an optional progress callback. The callback receives immutable progress snapshots so the scheduler can update FastAPI app state without coupling API code into the checker.

Candidate checking will change from protocol-wide gather to batch gather:

1. collect candidates grouped by protocol;
2. compute total candidates;
3. emit `running` progress with `checked = 0`;
4. for each protocol, split candidates into batches;
5. check one batch concurrently using the existing semaphore and `check_candidate()`;
6. append successful `CheckedProxy` results;
7. sort current successful proxies;
8. write the partial v2 document atomically;
9. emit progress with `checked`, `total`, `alive`, and `current_protocol`;
10. after all batches finish, write the final v2 document and return it.

Default batch size should be conservative and config-free for the first implementation, e.g. `500` candidates. It can become configurable later if needed.

## Scheduler/App State Changes

The scheduler will pass an `on_progress` callback to `run_pipeline()`. The app lifespan will store progress in `app.state.current_refresh`.

State updates should be simple dictionary assignment. The event loop is single-process in the current deployment, and the state is read by request handlers in the same process.

## Storage Semantics

Partial writes use the same `write_proxy_document()` function and preserve atomic replace semantics. The file remains a valid v2 document at all times.

`generated_at` should use the refresh start/check timestamp for all partial documents in the same refresh. This makes it clear that the file belongs to one active run.

## Error Handling

If a batch fails at the candidate level, existing `check_candidate()` behavior already converts per-proxy attempt failures into rejected proxies. If the whole pipeline raises an unexpected exception, the scheduler records `last_scheduler_error`, sets progress status to `failed`, and continues to the next scheduled refresh.

Already-written partial results stay available. A failed refresh should not delete a partial proxy document.

## Testing

Tests should cover:

- `run_pipeline()` writes after each completed batch, not only at the end;
- progress callback receives `running` updates with increasing `checked` count;
- final progress records total checked and alive count;
- `/stats` includes `current_refresh` while preserving existing aggregate fields;
- `/health` includes `refresh_running`;
- existing v2 response shapes and filters remain unchanged.

## Out Of Scope

- Database storage.
- Streaming HTTP responses.
- WebSocket/SSE progress.
- Persistent progress after process restart.
- Configurable batch size unless needed by tests or implementation constraints.
- Changing the v2 proxy item schema.
