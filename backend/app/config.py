from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


class Settings(BaseModel):
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    chroma_path: Path = Path(os.getenv("CHROMA_PATH", "./data/chroma"))
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    enable_reranking: bool = os.getenv("ENABLE_RERANKING", "false").lower() == "true"
    reranker_model: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    top_k: int = int(os.getenv("TOP_K", "6"))


settings = Settings()
SAMPLE_DOCS = Path(os.getenv("SAMPLE_DOCS_PATH", str(PROJECT_ROOT / "sample_docs")))
