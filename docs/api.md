# API

The API is served by FastAPI from `proxy_pool.app:app`.

## `GET /`

Without query parameters, `GET /` returns the full stored proxy JSON document.

Example response:

```json
{
  "total_count_of_proxies": 2,
  "http": [
    {
      "address": "1.2.3.4:8080",
      "countryCode": "US",
      "is_anonymous": true,
      "timeout": 0.42
    }
  ],
  "socks4": [],
  "socks5": [
    {
      "address": "5.6.7.8:1080",
      "countryCode": "DE",
      "is_anonymous": false,
      "timeout": 1.2
    }
  ]
}
```

If the result file does not exist or cannot be parsed, the API returns an empty document:

```json
{
  "total_count_of_proxies": 0,
  "http": [],
  "socks4": [],
  "socks5": []
}
```

## Filtered List Behavior

When any supported query parameter is present, `GET /` returns a flattened list instead of the full protocol-grouped document. Each row includes the original proxy fields plus `prototype`, which identifies the protocol bucket the proxy came from.

Example:

```http
GET /?prototypes=http,socks5&countrycodes=us&isanonymous=true&maxtimeout=0.5
```

Example response:

```json
[
  {
    "address": "1.2.3.4:8080",
    "countryCode": "US",
    "is_anonymous": true,
    "timeout": 0.42,
    "prototype": "http"
  }
]
```

## Query Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `prototypes` | comma-separated string | Filters by protocol. Values are matched case-insensitively against `http`, `socks4`, and `socks5`. |
| `countrycodes` | comma-separated string | Filters by `countryCode`, case-insensitively. |
| `isanonymous` | string boolean | Filters by `is_anonymous`. Use `true` or `false`. |
| `maxtimeout` | float | Keeps proxies whose `timeout` is less than or equal to the supplied value. |

Filters are combined with AND semantics.

## `GET /health`

Returns basic service and storage status.

Example response from the API service:

```json
{
  "status": "ok",
  "storage_path": "/app/data/proxies.json",
  "storage_exists": true,
  "scheduler_running": true,
  "last_scheduler_error": null
}
```

Fields:

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | Always `ok` when the app can serve the request. |
| `storage_path` | string | Effective result JSON path. |
| `storage_exists` | boolean | Whether the result JSON file currently exists. |
| `scheduler_running` | boolean | Present when scheduler state exists. `true` means the scheduler task exists and has not finished. |
| `last_scheduler_error` | string or null | Present when scheduler error tracking exists. Contains the most recent scheduler exception message, or `null`. |

When the app is created with `start_scheduler=False`, `scheduler_running` may be `false` and `last_scheduler_error` may be absent unless the app lifespan has initialized scheduler state.
