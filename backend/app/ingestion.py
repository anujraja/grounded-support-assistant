from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from .config import SAMPLE_DOCS, Settings, settings
from .models import Chunk, IngestResponse
from uuid import uuid4

import chromadb
from sentence_transformers import SentenceTransformer

try:
    from chromadb.config import Settings as ChromaSettings
except ImportError:  # lightweight test doubles do not expose Chroma internals
    ChromaSettings = None  # type: ignore[assignment,misc]


def chunk_markdown(text: str, chunk_size: int = 700, overlap: int = 120) -> list[tuple[str, str]]:
    """Return (heading, text) chunks while preserving a compact overlap."""
    normalized = re.sub(r"\r\n?", "\n", text).strip()
    sections = re.split(r"(?m)^(#{1,6}\s+.+)$", normalized)
    current_heading = ""
    pieces: list[tuple[str, str]] = []
    for part in sections:
        if not part.strip():
            continue
        if re.match(r"^#{1,6}\s+", part):
            current_heading = re.sub(r"^#+\s+", "", part).strip()
            continue
        words = part.strip().split()
        start = 0
        step = max(1, chunk_size - overlap)
        while start < len(words):
            chunk = " ".join(words[start : start + chunk_size])
            if chunk:
                pieces.append((current_heading, chunk))
            if start + chunk_size >= len(words):
                break
            start += step
    return pieces


class Embeddings:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            try:
                self._model = SentenceTransformer(self.model_name, local_files_only=True)
            except OSError:
                self._model = SentenceTransformer(self.model_name)
        return self._model.encode(texts, normalize_embeddings=True).tolist()


class DocumentStore:
    def __init__(self, app_settings: Settings = settings, client: object | None = None, embedder: object | None = None):
        self.settings = app_settings
        self.settings.chroma_path.mkdir(parents=True, exist_ok=True)
        if client is not None:
            self.client = client
        else:
            client_options = {"path": str(self.settings.chroma_path)}
            if ChromaSettings is not None:
                client_options["settings"] = ChromaSettings(anonymized_telemetry=False)
            self.client = chromadb.PersistentClient(**client_options)
        self.collection = self.client.get_or_create_collection(name="support_chunks", metadata={"hnsw:space": "cosine"})
        self.embedder = embedder or Embeddings(self.settings.embedding_model)

    def ingest_file(self, path: Path) -> tuple[int, bool]:
        return self.ingest_text(path.read_text(encoding="utf-8"), path.name)

    def ingest_text(self, text: str, filename: str) -> tuple[int, bool]:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = self.collection.get(where={"doc_hash": digest}, limit=1, include=[])
        if existing.get("ids"):
            return 0, True
        pairs = chunk_markdown(text)
        if not pairs:
            return 0, False
        created_at = datetime.now(timezone.utc).isoformat()
        chunks = [
            Chunk(id=str(uuid4()), text=body, filename=filename, heading=heading, created_at=created_at, doc_hash=digest)
            for heading, body in pairs
        ]
        self.collection.add(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.model_dump(exclude={"id", "text"}) for chunk in chunks],
            embeddings=self.embedder.embed([chunk.text for chunk in chunks]),
        )
        return len(chunks), False

    def ingest_paths(self, paths: Iterable[Path]) -> IngestResponse:
        ingested = skipped = 0
        files: list[str] = []
        for path in paths:
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            count, duplicate = self.ingest_file(path)
            ingested += count
            skipped += int(duplicate)
            files.append(path.name)
        return IngestResponse(ingested_chunks=ingested, skipped_duplicates=skipped, files=files)

    def all_chunks(self) -> list[Chunk]:
        result = self.collection.get(include=["documents", "metadatas"])
        return [
            Chunk(id=identifier, text=document, **metadata)
            for identifier, document, metadata in zip(result["ids"], result["documents"], result["metadatas"])
        ]

    def documents(self) -> list[dict[str, object]]:
        groups: dict[str, int] = {}
        for chunk in self.all_chunks():
            groups[chunk.filename] = groups.get(chunk.filename, 0) + 1
        return [{"filename": name, "chunks": count} for name, count in sorted(groups.items())]


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest fictional sample support documents")
    parser.add_argument("--samples", action="store_true", help="Ingest sample_docs from the repository")
    args = parser.parse_args()
    if args.samples:
        store = DocumentStore()
        print(store.ingest_paths(sorted(SAMPLE_DOCS.glob("*"))).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
