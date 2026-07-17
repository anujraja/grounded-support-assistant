from __future__ import annotations

from threading import Lock

from .models import AuditEvent


def _redact_text(value: str) -> str:
    import re

    value = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]", value)
    return re.sub(
        r"(?i)\b(authorization|api[_-]?key|token|secret|dsn)\s*[:=]\s*([^\s,]+)",
        r"\1=[REDACTED]",
        value,
    )


def _redact_data(value: object) -> object:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_redact_data(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_data(item) for key, item in value.items()}
    return value


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = Lock()

    def add(self, event: AuditEvent) -> AuditEvent:
        event.question = _redact_text(event.question)
        with self._lock:
            self._events.insert(0, event)
        return event

    def update_tool(self, proposal_id: str, approved: bool, result: dict[str, object] | None) -> None:
        with self._lock:
            for event in self._events:
                if event.tool_proposal_id == proposal_id:
                    event.tool_approved = approved
                    event.tool_result = _redact_data(result) if result is not None else None  # type: ignore[assignment]
                    break

    def list(self) -> list[AuditEvent]:
        with self._lock:
            return list(self._events)
