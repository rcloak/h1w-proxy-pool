# SQLite Dead Cache Design

## Goal

Avoid rechecking known-bad public proxies on every refresh. Persist failed proxy checks by `source_protocol + endpoint`, skip them for a bounded TTL, and retry later instead of permanently banning them.

## Problem

Public proxy lists repeat the same dead endpoints across refreshes. The checker currently deduplicates candidates only inside one collection pass, then checks every candidate again in later refreshes. This wastes most runtime on endpoints that recently failed.

## Approach

Use SQLite in the configured data directory. SQLite is in the Python standard library, works in Docker volumes, supports indexed lookups, and avoids adding a service or dependency.

## Data Model

Database path defaults to `Settings.save_path / "proxy_state.sqlite3"`.

Table `proxy_failures`:

```sql
CREATE TABLE IF NOT EXISTS proxy_failures (
  source_protocol TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  fail_count INTEGER NOT NULL,
  last_failed_at TEXT NOT NULL,
  last_error TEXT,
  skip_until TEXT NOT NULL,
  PRIMARY KEY (source_protocol, endpoint)
);
```

The key is protocol-sensitive because the same `ip:port` may behave differently as `http`, `socks4`, or `socks5`.

## Skip Policy

Use a simple exponential-ish backoff:

- 1st failure: skip 30 minutes.
- 2nd failure: skip 2 hours.
- 3rd failure: skip 6 hours.
- 4th+ failure: skip 24 hours.

If `skip_until > now`, the candidate is skipped before live checking. If `skip_until <= now`, the candidate is retried. If it succeeds, its failure row is removed. If it fails again, `fail_count` increments and `skip_until` is pushed forward.

## Integration

`run_pipeline()` will open the dead cache once per refresh when enabled. For each batch:

1. Filter candidates whose `(source_protocol, endpoint)` is still blocked.
2. Check only retryable candidates.
3. Record failures for checked candidates that returned no `CheckedProxy`.
4. Clear dead-cache rows for candidates that succeeded.
5. Continue partial proxy writes and progress updates as before.

Skipped candidates count as checked for progress because the refresh has made a decision for them in this cycle.

## Configuration

Add `[DeadCache]`:

```ini
[DeadCache]
Enabled = yes
DatabasePath = /app/data/proxy_state.sqlite3
```

If `DatabasePath` is empty, use `SavePath / proxy_state.sqlite3`. If the section is absent, enable dead-cache by default.

## API Stats

`GET /stats` adds:

```json
"dead_cache": {
  "enabled": true,
  "stored": 81234,
  "currently_skipped": 64000,
  "expired_retryable": 17234
}
```

If disabled, counts are zero and `enabled` is false.

## Error Handling

If SQLite operations fail unexpectedly, the refresh should fail visibly through existing scheduler error reporting. Silent failure would hide bad state and make operator statistics misleading.

## Out Of Scope

- Permanent bans.
- Separate API for deleting individual cache rows.
- Source-list quality scoring.
- Sharing SQLite across multiple running service replicas.
