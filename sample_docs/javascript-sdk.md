# JavaScript SDK initialization and supported examples

> Fictional demonstration content only. This is not official Sentry documentation.

## Initialization

Initialize the JavaScript SDK once, before creating application transactions. A valid example uses a DSN and a non-zero `tracesSampleRate` for tracing demonstration. Keep the DSN public key separate from private server credentials.

```ts
Sentry.init({ dsn: "https://public@example.invalid/42", tracesSampleRate: 0.2 });
```

## Support examples

For this demo, supported JavaScript SDK example versions are `7.120.0`, `8.0.0`, and `8.25.0`. Version `99.0` is not supported in the fictional matrix. Supported versions are examples for the demo only; do not use them as a release policy.

## Troubleshooting

If initialization is called twice, capture behavior can be confusing. Confirm the deployed bundle, the single initialization location, and the browser console before treating an SDK issue as a backend ingestion problem.
