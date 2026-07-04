from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    raw_dir: Path
    wiki_dir: Path
    staging_dir: Path
    sqlite_path: Path
    memory_backend: str
    memory_extractor: str
    mem0_api_key: str
    mem0_base_url: str
    langmem_model: str
    openai_base_url: str
    openai_api_key: str
    text_model: str
    vision_model: str


def load_settings() -> Settings:
    data_dir = Path(os.getenv("TRACEWIKI_DATA_DIR", "data"))
    return Settings(
        data_dir=data_dir,
        raw_dir=data_dir / "raw",
        wiki_dir=data_dir / "wiki",
        staging_dir=data_dir / "staging",
        sqlite_path=data_dir / "kb.sqlite",
        memory_backend=os.getenv("TRACEWIKI_MEMORY_BACKEND", "auto").lower(),
        memory_extractor=os.getenv("TRACEWIKI_MEMORY_EXTRACTOR", "langmem").lower(),
        mem0_api_key=os.getenv("MEM0_API_KEY", ""),
        mem0_base_url=os.getenv("MEM0_BASE_URL", "https://api.mem0.ai"),
        langmem_model=os.getenv("TRACEWIKI_LANGMEM_MODEL", "openai:gpt-4.1-mini"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        text_model=os.getenv("TRACEWIKI_TEXT_MODEL", "gpt-4.1-mini"),
        vision_model=os.getenv("TRACEWIKI_VISION_MODEL", "gpt-4.1-mini"),
    )


def ensure_dirs(settings: Settings) -> None:
    for path in [
        settings.raw_dir,
        settings.raw_dir / "docs",
        settings.raw_dir / "images",
        settings.raw_dir / "code",
        settings.raw_dir / "tables",
        settings.raw_dir / "web",
        settings.wiki_dir,
        settings.wiki_dir / "concepts",
        settings.wiki_dir / "sources",
        settings.wiki_dir / "outputs",
        settings.wiki_dir / "skills",
        settings.staging_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
