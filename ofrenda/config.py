"""Paths, Ollama, and the mock-model switch. Environment wins over .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines. Does not overwrite variables that are already set."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    sample_dir: Path
    ollama_host: str
    ollama_model: str
    mock_llm: bool
    llm_timeout: float
    segmenter_model: Path

    @property
    def tree_path(self) -> Path:
        return self.data_dir / "family.json"

    @property
    def portrait_dir(self) -> Path:
        return self.data_dir / "portraits"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


@lru_cache
def get_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    data_dir = Path(os.environ.get("OFRENDA_DATA_DIR", ROOT / "data")).expanduser()
    if not data_dir.is_absolute():
        data_dir = (ROOT / data_dir).resolve()
    model = Path(
        os.environ.get(
            "OFRENDA_SEGMENTER_MODEL",
            ROOT / "models" / "selfie_segmenter.tflite",
        )
    )
    return Settings(
        host=os.environ.get("OFRENDA_HOST", "127.0.0.1"),
        port=int(os.environ.get("OFRENDA_PORT", "8000")),
        data_dir=data_dir,
        sample_dir=ROOT / "sample",
        ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "gemma2:2b"),
        mock_llm=_flag("OFRENDA_MOCK_LLM"),
        llm_timeout=float(os.environ.get("OFRENDA_LLM_TIMEOUT", "120")),
        segmenter_model=model,
    )
