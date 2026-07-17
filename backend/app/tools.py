from __future__ import annotations

import re
from threading import Lock
from typing import Any

from pydantic import ValidationError

from .models import (
    CheckSupportedSDKArgs,
    ConfidenceResult,
    CreateEscalationSummaryArgs,
    InspectTraceHeadersArgs,
    ToolProposal,
)

SUPPORTED = {
    "javascript": {"7.120.0", "8.0.0", "8.25.0"},
    "python": {"1.45.0", "2.0.0"},
    "react-native": {"5.0.0"},
}
ARG_SCHEMAS = {
    "check_supported_sdk_version": CheckSupportedSDKArgs,
    "inspect_trace_headers": InspectTraceHeadersArgs,
    "create_escalation_summary": CreateEscalationSummaryArgs,
}


def check_supported_sdk_version(platform: str, version: str) -> dict[str, Any]:
    return {
        "platform": platform,
        "version": version,
        "supported": version in SUPPORTED[platform],
        "supported_demo_versions": sorted(SUPPORTED[platform]),
        "note": "Fictional demonstration matrix only.",
    }


def inspect_trace_headers(headers: dict[str, str]) -> dict[str, Any]:
    lowered = {key.lower(): value for key, value in headers.items()}
    present = [name for name in ("sentry-trace", "baggage") if lowered.get(name)]
    missing = [name for name in ("sentry-trace", "baggage") if name not in present]
    return {"present": present, "missing": missing, "complete_pair": not missing}


def create_escalation_summary(question: str, findings: list[str]) -> dict[str, Any]:
    return {
        "title": "Human support escalation",
        "question": question,
        "verified_findings": findings,
        "requested_next_step": "Review evidence and determine the minimum safe diagnostic action.",
    }


FUNCTIONS = {
    "check_supported_sdk_version": check_supported_sdk_version,
    "inspect_trace_headers": inspect_trace_headers,
    "create_escalation_summary": create_escalation_summary,
}


def validate_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    schema = ARG_SCHEMAS.get(tool_name)
    if schema is None:
        raise ValueError("Unknown or non-allowlisted tool")
    try:
        return schema.model_validate(arguments).model_dump()
    except ValidationError as exc:
        raise ValueError(f"Invalid tool arguments: {exc}") from exc


def propose_for_question(
    question: str,
    findings: list[str] | None = None,
    confidence: ConfidenceResult | None = None,
) -> ToolProposal | None:
    destructive = re.search(r"\b(delete|purge|destroy|disable|rotate|modify)\b", question, re.I)
    if destructive:
        return None
    version = re.search(r"\b(\d+(?:\.\d+){1,2})\b", question)
    platform = "react-native" if re.search(r"react[ -]native", question, re.I) else "python" if re.search(r"python", question, re.I) else "javascript"
    if version and re.search(r"sdk|version|supported", question, re.I):
        return ToolProposal(
            tool_name="check_supported_sdk_version",
            arguments={"platform": platform, "version": version.group(1)},
            reason="Compare the requested version with the deterministic fictional support matrix.",
        )
    if re.search(r"sentry-trace|baggage|trace headers?", question, re.I) and re.search(r"[:=]", question):
        headers: dict[str, str] = {}
        for name in ("sentry-trace", "baggage"):
            match = re.search(rf"{name}\s*[:=]\s*([^,\s]+)", question, re.I)
            if match:
                headers[name] = match.group(1)
        if headers:
            return ToolProposal(
                tool_name="inspect_trace_headers",
                arguments={"headers": headers},
                reason="Inspect only the header names and supplied demo values for the expected propagation pair.",
            )
    if confidence and confidence.escalation_recommended:
        safe_findings = (findings or ["The local knowledge base did not provide sufficient verified evidence."])[:10]
        return ToolProposal(
            tool_name="create_escalation_summary",
            arguments={"question": question, "findings": safe_findings},
            reason="Prepare a deterministic handoff because the evidence heuristic recommends escalation.",
        )
    return None


class ToolRegistry:
    def __init__(self) -> None:
        self._proposals: dict[str, ToolProposal] = {}
        self._decisions: dict[str, bool] = {}
        self._lock = Lock()

    def save(self, proposal: ToolProposal) -> ToolProposal:
        proposal.arguments = validate_tool_arguments(proposal.tool_name, proposal.arguments)
        with self._lock:
            self._proposals[proposal.id] = proposal
        return proposal

    def execute(self, proposal_id: str, approved: bool) -> tuple[ToolProposal, dict[str, Any] | None]:
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            already_decided = proposal_id in self._decisions
        if proposal is None:
            raise ValueError("Unknown proposal; tools can only execute from a stored proposal")
        if already_decided:
            raise ValueError("This tool proposal has already been approved or rejected")
        with self._lock:
            self._decisions[proposal_id] = approved
        if not approved:
            return proposal, None
        arguments = validate_tool_arguments(proposal.tool_name, proposal.arguments)
        return proposal, FUNCTIONS[proposal.tool_name](**arguments)
