# Source-map upload troubleshooting

> Fictional demonstration content only. This is not official Sentry documentation.

## Matching release artifacts

Source maps resolve minified stack frames only when the uploaded artifacts use the same release name and distribution as the browser bundle. Confirm `release` is identical in the SDK and upload command. A mismatched `dist` can prevent artifact lookup.

## Error examples

`SMAP-404` means no matching artifact was found for the requested release. `SMAP-422` means the upload manifest was malformed. Keep source maps private and do not include application secrets in uploaded sources.

## Safe investigation

Collect the release name, artifact filename, and non-secret upload log lines. If the application is customer-managed or artifacts cannot be inspected safely, create an escalation summary rather than requesting production access.
