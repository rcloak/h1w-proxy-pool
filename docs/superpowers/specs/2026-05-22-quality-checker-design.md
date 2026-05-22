# Quality Checker Design

Date: 2026-05-22

## Goal

Improve proxy validation from a single endpoint liveness check into a quality-oriented checker that measures reliability, protocol capability, latency, anonymity, and score while preserving the existing JSON API shape.

## Current State

The current checker treats a proxy as alive when one request through the proxy reaches `http://ip-api.com/json/?fields=8219` and returns valid `query` and `countryCode` fields.

This works, but it has limitations:

- A single public endpoint is a single point of failure.
- Rate limiting or transient endpoint failures can reject otherwise working proxies.
- HTTP and HTTPS capability are not measured separately.
- A single successful request does not measure stability.
- The result contains timeout and anonymity, but not success rate, failure reason, or quality score.

## Chosen Approach

Implement the full quality checker option:

- Multi-endpoint checking.
- Repeated attempts per proxy.
- HTTP and HTTPS capability flags.
- Quality metrics and scoring.
- Additional API filters for quality fields.
- Backward-compatible JSON fields.
- No database in this phase.

The checker will store quality metrics for the latest refresh in `proxies.json`. Long-term historical reputation is explicitly out of scope for this phase.

## Configuration

Add a `[Checker]` section to `config.ini`:

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

Semantics:

- `Endpoints`: endpoint URLs used to verify the proxy and discover the observed outbound IP.
- `AttemptsPerProxy`: number of times to try each endpoint/capability combination.
- `RequiredSuccesses`: minimum successful attempts required for a proxy to be kept.
- `CheckHttp`: whether to check HTTP capability.
- `CheckHttps`: whether to check HTTPS capability.
- `MinSuccessRate`: minimum success rate required for a proxy to be kept.

Existing configs without `[Checker]` must continue to work using safe defaults equivalent to the example above.

## Endpoint Response Parsing

The checker must support common IP echo response shapes:

- `{"query": "1.2.3.4", "countryCode": "US"}`
- `{"origin": "1.2.3.4"}`
- `{"ip": "1.2.3.4"}`

If `countryCode` is unavailable, the checker should keep an empty country code rather than rejecting the proxy, provided the observed outbound IP is present.

Malformed JSON, missing outbound IP, invalid IP shape, HTTP errors, timeouts, and connector failures count as failed attempts.

## Protocol Capability Checks

Each proxy is evaluated for enabled capabilities:

- HTTP capability: request an HTTP endpoint through the proxy.
- HTTPS capability: request an HTTPS endpoint through the proxy.

For `http` proxies, HTTPS checks verify HTTP CONNECT behavior through an HTTPS endpoint.

For `socks4` and `socks5`, both HTTP and HTTPS endpoint requests use the SOCKS connector with the corresponding proxy scheme.

Capabilities are recorded independently:

- `supports_http`
- `supports_https`

At least one enabled capability must succeed for the proxy to be retained.

## Metrics

Each retained proxy item includes existing fields:

- `address`
- `countryCode`
- `is_anonymous`
- `timeout`

It also includes quality fields:

- `score`: numeric quality score, higher is better.
- `success_rate`: successful attempts divided by total attempts.
- `success_count`: number of successful attempts.
- `failure_count`: number of failed attempts.
- `supports_http`: boolean.
- `supports_https`: boolean.
- `avg_timeout`: average successful attempt timeout.
- `last_error`: most recent failure message or `null`.
- `checked_at`: ISO-8601 UTC timestamp for the check.

`timeout` remains for compatibility and should equal `avg_timeout` for retained proxies.

## Scoring

Use a deterministic score that favors reliability, HTTPS support, anonymity, and lower latency:

```text
score = success_rate * 70
      + supports_https * 15
      + is_anonymous * 10
      - latency_penalty
```

`latency_penalty` should be bounded so a slow working proxy is penalized but not driven below zero solely because it is slow. Final score should be clamped to `0..100`.

Sorting should prefer higher `score`, then lower `avg_timeout`, then natural address order.

## JSON Compatibility

The top-level JSON shape remains:

```json
{
  "total_count_of_proxies": 0,
  "http": [],
  "socks4": [],
  "socks5": []
}
```

Existing consumers reading only `address`, `countryCode`, `is_anonymous`, and `timeout` should continue to work.

Storage reading must accept older proxy items that do not yet have quality fields, normalize what it can, and not crash the API.

## API Changes

Existing `GET /` behavior remains.

Add optional filters:

- `minscore`: keep proxies with `score >= minscore`.
- `supportshttps`: boolean filter for `supports_https`.
- `minsuccessrate`: keep proxies with `success_rate >= minsuccessrate`.

Existing filters continue to work:

- `prototypes`
- `countrycodes`
- `isanonymous`
- `maxtimeout`

When quality fields are missing from older stored data, filters should treat missing values conservatively:

- missing `score` means `0`
- missing `success_rate` means `0`
- missing `supports_https` means `false`

## Testing

Network-heavy behavior must be tested with mocked sessions/connectors or pure helper functions. Unit tests should not require live proxy sources.

Required test coverage:

- IP extraction from `query`, `origin`, and `ip` response shapes.
- Rejection of malformed JSON and missing outbound IP.
- Repeated attempt aggregation.
- Success rate and failure count calculation.
- HTTP and HTTPS capability flags.
- Score calculation and clamping.
- Sorting by score, average timeout, and natural address.
- API filters for `minscore`, `supportshttps`, and `minsuccessrate`.
- Storage compatibility with older JSON items.

## Non-Goals

- Long-term historical reputation across many refresh cycles.
- Database-backed proxy history.
- UI for proxy quality.
- Guaranteeing public proxy reliability beyond the latest measured state.

## Acceptance Criteria

The phase is complete when:

- `[Checker]` configuration is supported with safe defaults.
- Checker uses multiple endpoints and repeated attempts.
- Retained proxies include quality fields while preserving existing fields.
- API supports the new quality filters.
- Sorting prefers high quality proxies.
- Tests cover parsing, aggregation, scoring, filtering, and storage compatibility without live network dependency.
- `uv run pytest` passes.
- Docker image still builds.
