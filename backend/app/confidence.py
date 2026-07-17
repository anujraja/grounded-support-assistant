from __future__ import annotations

import re

from .models import ConfidenceResult, RetrievedChunk

OUT_OF_SCOPE_PATTERNS = (
    r"not covered",
    r"unrelated",
    r"unknown product",
    r"weather|stock price|medical|legal",
)


def calculate_confidence(question: str, chunks: list[RetrievedChunk], agreement: float = 0.0) -> ConfidenceResult:
    if not chunks:
        return ConfidenceResult(
            label="Low confidence",
            score=0.0,
            explanation="No supporting chunks were retrieved.",
            escalation_recommended=True,
        )
    best = chunks[0].combined_score
    supporting = sum(chunk.combined_score >= 0.38 for chunk in chunks)
    absent_signal = any(re.search(pattern, question, re.I) for pattern in OUT_OF_SCOPE_PATTERNS)
    score = min(1.0, 0.55 * best + 0.25 * agreement + 0.2 * min(1.0, supporting / 3))
    if absent_signal:
        score *= 0.25
    score = round(score, 3)
    if score >= 0.67:
        label = "High confidence"
    elif score >= 0.4:
        label = "Medium confidence"
    else:
        label = "Low confidence"
    explanation = f"Best fused score {best:.2f}; retrieval agreement {agreement:.2f}; {supporting} supporting chunk(s)."
    if absent_signal:
        explanation += " The question explicitly signals missing corpus coverage."
    return ConfidenceResult(
        label=label,
        score=score,
        explanation=explanation,
        escalation_recommended=label == "Low confidence",
    )
