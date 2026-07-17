from __future__ import annotations

from sentence_transformers import CrossEncoder

from .models import RetrievedChunk


class OptionalReranker:
    def __init__(self, model_name: str, enabled: bool = False):
        self.model_name = model_name
        self.enabled = enabled
        self._model: CrossEncoder | None = None
        self.last_error: str | None = None

    def rerank(self, question: str, chunks: list[RetrievedChunk], enabled: bool | None = None) -> list[RetrievedChunk]:
        should_run = self.enabled if enabled is None else enabled
        if not should_run or not chunks:
            return chunks
        try:
            if self._model is None:
                try:
                    self._model = CrossEncoder(self.model_name, local_files_only=True)
                except OSError:
                    self._model = CrossEncoder(self.model_name)
            scores = self._model.predict([(question, chunk.text) for chunk in chunks])
            for chunk, score in zip(chunks, scores):
                chunk.rerank_score = float(score)
            chunks.sort(key=lambda item: item.rerank_score or float("-inf"), reverse=True)
            for rank, chunk in enumerate(chunks, 1):
                chunk.final_rank = rank
        except Exception as exc:  # optional feature must degrade cleanly
            self.last_error = str(exc)
        return chunks
