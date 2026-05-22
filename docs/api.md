# API

The API is served by FastAPI from `proxy_pool.app:app`.

The service has two related JSON shapes:

- API list responses from `GET /` and `GET /proxies`: `{ "total": number, "items": [...] }`.
- Storage file written on disk: `{ "version": 2, "generated_at": string, "total": number, "items": [...] }`.

Clients should use the API shape unless they intentionally read the JSON file directly.

## Base URL

Local and Docker defaults use:

```text
http://localhost:5000
```

Useful commands:

```sh
curl http://localhost:5000/health
curl http://localhost:5000/proxies
curl 'http://localhost:5000/proxies?usable_as=https&min_score=80&limit=20'
curl http://localhost:5000/stats
```

## `GET /proxies`

Returns the current v2 proxy list from the result JSON file. The response is always a list document with a `total` count and `items` array, including when filters are supplied. Items are sorted by quality score descending, average latency ascending, then endpoint ascending.

Example response:

```json
{
  "total": 2,
  "items": [
    {
      "endpoint": "1.2.3.4:8080",
      "source_protocol": "http",
      "usable_as": ["http", "https"],
      "quality": {
        "score": 90.8,
        "success_rate": 1.0,
        "checks_passed": 4,
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
    },
    {
      "endpoint": "5.6.7.8:1080",
      "source_protocol": "socks5",
      "usable_as": ["http"],
      "quality": {
        "score": 40.5,
        "success_rate": 0.75,
        "checks_passed": 3,
        "checks_failed": 1,
        "avg_latency_ms": 1200,
        "last_error": "TimeoutError"
      },
      "network": {
        "exit_ip": "5.6.7.8",
        "country_code": "DE",
        "anonymous": false
      },
      "timestamps": {
        "checked_at": "2026-05-22T12:00:00Z"
      }
    }
  ]
}
```

If the result file does not exist or cannot be parsed, the API returns an empty v2 list:

```json
{
  "total": 0,
  "items": []
}
```

## `GET /`

Returns the same response shape and supports the same filters as `GET /proxies`.

## Query Parameters

Filters are combined with AND semantics. Filtered responses keep the same `{ "total", "items" }` shape and `total` is the number of returned items after filtering and limiting.

Example:

```http
GET /proxies?source_protocol=http&usable_as=https&min_score=80&min_success_rate=0.9&country=us&anonymous=true&limit=10
```

| Parameter | Type | Description |
| --- | --- | --- |
| `source_protocol` | string | Filters by the protocol used to connect to the proxy. Accepted values are `http`, `socks4`, and `socks5`, matched case-insensitively. |
| `usable_as` | string | Keeps proxies that successfully reached the requested destination capability. Accepted values are `http` and `https`, matched case-insensitively. |
| `min_score` | float | Keeps proxies whose `quality.score` is greater than or equal to the supplied value. `nan`, `inf`, and `-inf` are rejected with HTTP 422. |
| `min_success_rate` | float | Keeps proxies whose `quality.success_rate` is greater than or equal to the supplied value. `nan`, `inf`, and `-inf` are rejected with HTTP 422. |
| `country` | string | Filters by `network.country_code`, matched case-insensitively. |
| `anonymous` | string boolean | Filters by `network.anonymous`. Use `true` or `false`. |
| `limit` | integer | Limits the number of returned items. Values must be positive and are capped at `1000`. |

Example use cases:

```sh
# Best 50 HTTPS-capable proxies, regardless of source protocol.
curl 'http://localhost:5000/proxies?usable_as=https&limit=50'

# Strong HTTP source proxies that can also reach HTTPS destinations.
curl 'http://localhost:5000/proxies?source_protocol=http&usable_as=https&min_score=80&min_success_rate=0.9'

# Anonymous SOCKS5 proxies from the United States.
curl 'http://localhost:5000/proxies?source_protocol=socks5&anonymous=true&country=US'
```

## Proxy Item Fields

Each item describes one checked proxy endpoint.

| Field | Type | Description |
| --- | --- | --- |
| `endpoint` | string | Proxy endpoint as `ip:port`. |
| `source_protocol` | string | Protocol used to connect to the proxy candidate: `http`, `socks4`, or `socks5`. |
| `usable_as` | array | Destination capabilities that passed checks through this proxy: `http`, `https`, or both. |
| `quality.score` | float | Quality score from `0.0` to `100.0`, based on success rate, HTTPS capability, anonymity, and latency. |
| `quality.success_rate` | float | Successful attempts divided by total attempts, from `0.0` to `1.0`. |
| `quality.checks_passed` | integer | Number of successful endpoint attempts. |
| `quality.checks_failed` | integer | Number of failed endpoint attempts. |
| `quality.avg_latency_ms` | integer | Average latency in milliseconds across successful attempts. |
| `quality.last_error` | string or null | Most recent failed attempt error class or checker error message, when any attempt failed. |
| `network.exit_ip` | string | IP address observed by a successful check endpoint. |
| `network.country_code` | string | Country code reported by a successful check endpoint, or an empty string. |
| `network.anonymous` | boolean | Whether a successful attempt observed an exit IP different from the candidate IP. |
| `timestamps.checked_at` | string | UTC timestamp for the check cycle that produced the item. |

`source_protocol` and `usable_as` are intentionally separate. `source_protocol` is how Proxy Pool connects to the proxy itself. `usable_as` is what destination protocol worked through that proxy during live checks. For example, a proxy can have `source_protocol: "socks5"` and `usable_as: ["http", "https"]`.

Endpoint validation is strict `ip:port`. Ports must be decimal digits in the `1` to `65535` range.

## `GET /stats`

Returns aggregate information for the current stored v2 document.

Example response:

```json
{
  "total": 2,
  "by_source_protocol": {
    "http": 1,
    "socks4": 0,
    "socks5": 1
  },
  "by_capability": {
    "http": 2,
    "https": 1
  },
  "last_refresh": {
    "started_at": "2026-05-22T12:00:00+00:00",
    "finished_at": "2026-05-22T12:00:05+00:00",
    "duration_seconds": 5.0,
    "proxies_alive": 2
  },
  "current_refresh": {
    "status": "running",
    "started_at": "2026-05-22T12:05:00+00:00",
    "finished_at": null,
    "checked": 120,
    "total": 500,
    "alive": 18,
    "current_protocol": "http"
  }
}
```

If no scheduler refresh metadata exists yet, `last_refresh.started_at`, `last_refresh.finished_at`, and `last_refresh.duration_seconds` are `null`, and `last_refresh.proxies_alive` is `0`.

`last_refresh` is process memory, not data loaded from the JSON file. After a restart it starts empty until the scheduler completes a refresh.

`current_refresh` reports refresh progress state:

- Initial idle before any refresh: `status: "idle"`, `started_at: null`, `finished_at: null`, `checked: 0`, `total: 0`, `alive: 0`, and `current_protocol: null`.
- Running refresh: `status: "running"`; `checked`, `total`, and `alive` advance as batches complete; `finished_at` remains `null`.
- Completed refresh: `status: "idle"` with final `checked`, `total`, and `alive` counts preserved, `finished_at` set, and `current_protocol: null`.
- Failed refresh: `status: "failed"` with last known `checked`, `total`, and `alive` counts preserved and `finished_at` set.

`current_refresh` fields:

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | Refresh state: `idle`, `running`, or `failed`. |
| `started_at` | string or null | UTC timestamp when the current refresh started. |
| `finished_at` | string or null | UTC timestamp when the refresh completed or failed. `null` before the first terminal state and while running. |
| `checked` | integer | Number of candidate proxies checked so far, or the final checked count after completion/failure. |
| `total` | integer | Total candidate proxies expected in the current refresh, or the final total after completion/failure. |
| `alive` | integer | Number of verified proxies found so far, or the final alive count after completion/failure. |
| `current_protocol` | string or null | Source protocol currently being checked, last known protocol after failure, or `null` when initially idle or after successful completion. |

## `GET /health`

Returns basic service and storage status.

Example response from the API service:

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

Fields:

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | Always `ok` when the app can serve the request. |
| `storage_path` | string | Effective result JSON path. |
| `storage_exists` | boolean | Whether the result JSON file currently exists. |
| `scheduler_running` | boolean | Present when scheduler state exists. `true` means the scheduler task exists and has not finished. |
| `last_scheduler_error` | string or null | Present when scheduler error tracking exists. Contains the most recent scheduler exception message, or `null`. |
| `refresh_running` | boolean | Present when refresh progress state exists. `true` means `current_refresh.status` is `running`. |

When the app is created with `start_scheduler=False`, `scheduler_running` may be `false` and `last_scheduler_error` may be absent unless the app lifespan has initialized scheduler state.

## OpenAPI

FastAPI also exposes generated documentation when the service is running:

- Swagger UI: `http://localhost:5000/docs`
- OpenAPI JSON: `http://localhost:5000/openapi.json`
