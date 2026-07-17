# Escalation and safety policy

> Fictional demonstration content only. This is not official Sentry documentation.

## Escalate to a human engineer

Escalate when the supplied evidence does not cover the request, when results conflict, when a customer reports potential data exposure, or when an issue requires production access. State what was verified, what remains a hypothesis, and the minimum safe next observation.

## No destructive actions

This demo never deletes projects, changes account settings, deploys code, accesses production systems, or sends network requests. Requests to delete, purge, disable, rotate, or modify customer resources must be refused and escalated. There is no allowlisted destructive tool.

## Audit record

Record the user question, retrieved chunk IDs, tool proposal and decision, deterministic tool result, confidence label, escalation recommendation, and timestamp. Never record secrets or full environment values.
