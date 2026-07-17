# Distributed tracing: frontend to backend

> Fictional demonstration content only. This is not official Sentry documentation.

## Trace propagation

Browser and backend spans join one distributed trace when the browser sends both the `sentry-trace` and `baggage` headers to an allowed backend origin. Configure the JavaScript SDK's `tracePropagationTargets` with the exact API origin or a deliberate regular expression. The default does not imply that every cross-origin request is eligible.

Example:

```ts
Sentry.init({
  dsn: "https://public@example.invalid/42",
  tracesSampleRate: 0.2,
  tracePropagationTargets: ["localhost", /^https:\/\/api\.demo\.internal/],
});
```

## `sentry-trace` and `baggage`

`sentry-trace` carries trace identity and sampling state so an upstream transaction can be continued. `baggage` carries vendor-neutral dynamic sampling context. Forward both headers unchanged through reverse proxies and CORS middleware. Do not copy these headers from one user request into another.

## Common connection failures

- The frontend target does not match the actual backend origin.
- CORS `Access-Control-Allow-Headers` omits `sentry-trace` or `baggage`.
- A proxy strips unknown request headers.
- Browser sampling is disabled with `tracesSampleRate: 0`.

Verify the browser Network panel and backend request logs before changing sampling. A missing parent span is a diagnosis hypothesis until headers and target configuration are verified.
