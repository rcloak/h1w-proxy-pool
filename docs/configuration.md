# Configuration

Proxy Pool reads configuration from `config.ini` by default. The API service loads it during app creation when no explicit result path is supplied, and `proxy-pool-scrape` loads it before running a one-off refresh.

## General

`[General]` controls checking, sorting, storage, and scheduler cadence.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `Timeout` | float | `10` | Seconds to wait for each checked proxy request. Fractional values are accepted. |
| `MaxConnections` | integer | `900` | Maximum concurrent proxy checks. Keep this bounded to avoid local resource exhaustion. |
| `SortBySpeed` | boolean | `yes` | When enabled, output proxies are sorted by quality score, average timeout, then address. When disabled, they are sorted by address. |
| `SavePath` | path | directory containing `config.ini` | Directory where the result file is written. An empty value means the config file directory. Docker uses `/app/data`. |
| `JsonResultFilename` | string | `proxies.json` | Result JSON filename. The effective path is `SavePath / JsonResultFilename`. |
| `SaveFormat` | string | `json` | Configured output format. The current implementation writes JSON. |
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

Proxy sources are grouped by protocol in `[HTTP]`, `[SOCKS4]`, and `[SOCKS5]` sections.

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

Only enabled sections with at least one source URL are passed to the scrape/check pipeline.

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

Checker endpoints must return JSON containing one of `query`, `origin`, or `ip`. `countryCode` is optional and is preserved when present.

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
