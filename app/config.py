from dataclasses import dataclass
import os
from pathlib import Path


def _int_env(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    chat_model: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2")
    embed_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    data_dir: Path = Path(os.getenv("RAG_DATA_DIR", "./data"))
    chunk_size: int = _int_env("CHUNK_SIZE", 800, 100)
    chunk_overlap: int = _int_env("CHUNK_OVERLAP", 120, 0)
    top_k: int = _int_env("TOP_K", 4, 1)

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

