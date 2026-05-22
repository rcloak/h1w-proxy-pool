# Configuration

Proxy Pool reads configuration from `config.ini` by default. The API service loads it during app creation when no explicit result path is supplied, and `proxy-pool-scrape` loads it before running a one-off refresh.

## General

`[General]` controls checking, sorting, storage, and scheduler cadence.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `Timeout` | float | `10` | Seconds to wait for each checked proxy request. Fractional values are accepted. |
| `MaxConnections` | integer | `900` | Maximum concurrent proxy checks. Keep this bounded to avoid local resource exhaustion. |
| `SortBySpeed` | boolean | `yes` | When enabled, output proxies are sorted by quality score, average latency, then endpoint. When disabled, they are sorted by endpoint. |
| `SavePath` | path | directory containing `config.ini` | Directory where the result file is written. An empty value means the config file directory. Docker uses `/app/data`. |
| `JsonResultFilename` | string | `proxies.json` | Result JSON filename. The effective path is `SavePath / JsonResultFilename`. |
| `SaveFormat` | string | `json` | Configured output format. The current implementation writes only JSON; legacy folder output is not active. |
| `RefreshIntervalSeconds` | integer | `900` | Seconds the API scheduler waits between scrape/check cycles. |

Example:

```ini
[General]
Timeout = 10
MaxConnections = 800
SortBySpeed = yes
SavePath = /app/data
JsonResultFilename = proxies.json
SaveFormat = json
RefreshIntervalSeconds = 900
```

## Source Sections

Proxy sources are grouped by source protocol in `[HTTP]`, `[SOCKS4]`, and `[SOCKS5]` sections. The section name becomes each item's `source_protocol` when a proxy from that section passes live checks.

Each section supports:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `Enabled` | boolean | `yes` | Enables or disables the section. If omitted, the section is treated as enabled. |
| `Sources` | multiline URL list | empty | Source URLs to fetch. Blank lines are ignored. |

Example:

```ini
[HTTP]
Enabled = yes
Sources =
    https://example.test/http.txt
    https://example.test/more-http.txt

[SOCKS4]
Enabled = no
Sources =
    https://example.test/socks4.txt

[SOCKS5]
Enabled = yes
Sources =
    https://example.test/socks5.txt
```

Only enabled sections with at least one source URL are passed to the scrape/check pipeline. Source lists may contain noise; the scraper extracts strict `ip:port` candidates and deduplicates them per protocol.

## Checker

`[Checker]` controls the live proxy quality checks used to produce scored output.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `Endpoints` | multiline URL list | `http://httpbin.org/ip`, `https://api.ipify.org?format=json`, `http://ip-api.com/json/?fields=8219` | Public IP endpoints used for validation. Blank values fall back to the defaults. HTTP endpoints test HTTP capability; HTTPS endpoints test HTTPS capability. |
| `AttemptsPerProxy` | integer | `2` | Number of times to repeat the enabled capability checks for each candidate. Values below `1` are clamped to `1`; invalid values use the default. |
| `RequiredSuccesses` | integer | `1` | Minimum successful attempts required for a proxy to be kept. Values below `1` are clamped to `1`; invalid values use the default. |
| `CheckHttp` | boolean | `yes` | Enables checks against `http://` endpoints. If both `CheckHttp` and `CheckHttps` are disabled, HTTP checks are re-enabled so the checker has at least one capability to test. |
| `CheckHttps` | boolean | `yes` | Enables checks against `https://` endpoints. |
| `MinSuccessRate` | float | `0.5` | Minimum successful-attempt ratio required for a proxy to be kept. Values are clamped to the `0.0` to `1.0` range; invalid values use the default. |

Example:

```ini
[Checker]
Endpoints =
    http://httpbin.org/ip
    https://api.ipify.org?format=json
    http://ip-api.com/json/?fields=8219
AttemptsPerProxy = 2
RequiredSuccesses = 1
CheckHttp = yes
CheckHttps = yes
MinSuccessRate = 0.5
```

Checker endpoints must return JSON containing an observed IP in `query`, `origin`, or `ip`. Country metadata is optional and is preserved in `network.country_code` when present as `countryCode`.

`CheckHttp` enables attempts against `http://` checker endpoints. `CheckHttps` enables attempts against `https://` checker endpoints. Successful HTTP attempts add `http` to `usable_as`; successful HTTPS attempts add `https` to `usable_as`.

## Dead Cache

`[DeadCache]` controls SQLite persistence for failed proxy checks. It is enabled by default when the section is absent.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `Enabled` | boolean | `yes` | Enables skipping recently failed proxies in later refreshes. |
| `DatabasePath` | path | `SavePath / proxy_state.sqlite3` | SQLite database path. Docker uses `/app/data/proxy_state.sqlite3`. Empty value uses the default path. |

Example:

```ini
[DeadCache]
Enabled = yes
DatabasePath = /app/data/proxy_state.sqlite3
```

The cache key is `source_protocol + endpoint`, so the same `ip:port` can have separate failure history for `http`, `socks4`, and `socks5`. Failed checks are skipped temporarily with backoff: 30 minutes, 2 hours, 6 hours, then 24 hours for later failures. Successful checks clear the cache row.

## Output Shape

The configured result file is written as a v2 proxy document:

```json
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 0,
  "items": []
}
```

Each item includes `endpoint`, `source_protocol`, `usable_as`, `quality`, `network`, and `timestamps`. `source_protocol` is the protocol used to connect to the proxy candidate, while `usable_as` lists the HTTP and HTTPS destination capabilities that succeeded during checking.

The API intentionally omits storage-only `version` and `generated_at` from list responses. `GET /` and `GET /proxies` return `{ "total", "items" }`.

## Folders Section

The sample config includes a `[Folders]` section for legacy compatibility:

```ini
[Folders]
proxies = yes
proxies_anonymous = yes
proxies_geolocation = yes
proxies_geolocation_anonymous = yes
```

The current implementation does not read these fields; JSON output is controlled by `[General]`.
