from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .config import Settings, settings
from .models import RetrievedChunk

SYSTEM_PROMPT = """You are a grounded technical support assistant for a fictional demonstration.
Use only the supplied evidence for factual product claims. Never invent configuration values, API behavior, or supported versions.
If evidence is insufficient, say so clearly and recommend human escalation.
Cite claims with only the supplied citation labels such as [1] and [2]. Do not create any other citations.
Use this exact two-section structure, even if the second section says that no hypothesis is needed:
Verified findings
<evidence-backed findings with citations>
Possible diagnostic hypotheses
<clearly labeled hypotheses or "None needed for this question">
Keep the answer concise and operational.
You cannot execute tools; tool proposals are handled separately by the application."""


def build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    context = "\n\n".join(
        f"[{index}] {chunk.filename} - {chunk.heading or 'Document'}\n{chunk.text}"
        for index, chunk in enumerate(chunks, 1)
    )
    return f"{SYSTEM_PROMPT}\n\nEVIDENCE\n{context or 'No retrieved evidence.'}\n\nQUESTION\n{question}\n\nANSWER"


async def stream_ollama(question: str, chunks: list[RetrievedChunk], app_settings: Settings = settings) -> AsyncIterator[str]:
    payload = {"model": app_settings.ollama_model, "prompt": build_prompt(question, chunks), "stream": True}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=4.0)) as client:
            async with client.stream("POST", f"{app_settings.ollama_base_url.rstrip('/')}/api/generate", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get("response"):
                        yield item["response"]
                    if item.get("done"):
                        break
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        yield (
            "Ollama is unavailable, so no model-generated product answer was produced. "
            "Start Ollama and confirm the configured model is pulled. "
            f"Technical detail: {type(exc).__name__}."
        )
