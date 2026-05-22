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
      "timeout": 0.42,
      "score": 90.8,
      "success_rate": 1.0,
      "success_count": 4,
      "failure_count": 0,
      "supports_http": true,
      "supports_https": true,
      "avg_timeout": 0.42,
      "last_error": null,
      "checked_at": "2026-05-22T12:00:00Z"
    }
  ],
  "socks4": [],
  "socks5": [
    {
      "address": "5.6.7.8:1080",
      "countryCode": "DE",
      "is_anonymous": false,
      "timeout": 1.2,
      "score": 40.5,
      "success_rate": 0.75,
      "success_count": 3,
      "failure_count": 1,
      "supports_http": true,
      "supports_https": false,
      "avg_timeout": 1.2,
      "last_error": "TimeoutError",
      "checked_at": "2026-05-22T12:00:00Z"
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
GET /?prototypes=http,socks5&countrycodes=us&isanonymous=true&maxtimeout=0.5&minscore=80&supportshttps=true&minsuccessrate=0.9
```

Example response:

```json
[
  {
    "address": "1.2.3.4:8080",
    "countryCode": "US",
    "is_anonymous": true,
    "timeout": 0.42,
    "score": 90.8,
    "success_rate": 1.0,
    "success_count": 4,
    "failure_count": 0,
    "supports_http": true,
    "supports_https": true,
    "avg_timeout": 0.42,
    "last_error": null,
    "checked_at": "2026-05-22T12:00:00Z",
    "prototype": "http"
  }
]
```

## Proxy Quality Fields

Checked proxy rows include the legacy fields plus quality metadata:

| Field | Type | Description |
| --- | --- | --- |
| `score` | float | Quality score from `0.0` to `100.0`, based on success rate, HTTPS support, anonymity, and latency. |
| `success_rate` | float | Successful attempts divided by total attempts, from `0.0` to `1.0`. |
| `success_count` | integer | Number of successful endpoint attempts. |
| `failure_count` | integer | Number of failed endpoint attempts. |
| `supports_http` | boolean | Whether at least one HTTP endpoint attempt succeeded. |
| `supports_https` | boolean | Whether at least one HTTPS endpoint attempt succeeded. |
| `avg_timeout` | float | Average timeout in seconds across successful attempts. |
| `last_error` | string or null | Most recent failed attempt error class or checker error message, when any attempt failed. |
| `checked_at` | string | UTC timestamp for the check cycle that produced the row. |

## Query Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `prototypes` | comma-separated string | Filters by protocol. Values are matched case-insensitively against `http`, `socks4`, and `socks5`. |
| `countrycodes` | comma-separated string | Filters by `countryCode`, case-insensitively. |
| `isanonymous` | string boolean | Filters by `is_anonymous`. Use `true` or `false`. |
| `maxtimeout` | float | Keeps proxies whose `timeout` is less than or equal to the supplied value. |
| `minscore` | float | Keeps proxies whose `score` is greater than or equal to the supplied value. `nan`, `inf`, and `-inf` are rejected with HTTP 422. |
| `supportshttps` | string boolean | Filters by `supports_https`. Use `true` or `false`. |
| `minsuccessrate` | float | Keeps proxies whose `success_rate` is greater than or equal to the supplied value. `nan`, `inf`, and `-inf` are rejected with HTTP 422. |

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
