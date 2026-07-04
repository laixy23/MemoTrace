from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from tracewiki.config import Settings, load_settings
from tracewiki.storage import KnowledgeStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    os.environ.setdefault("TRACEWIKI_DATA_DIR", str(PROJECT_ROOT / "data"))
    return load_settings()


@lru_cache(maxsize=1)
def get_store() -> KnowledgeStore:
    settings = get_settings()
    return KnowledgeStore(settings.sqlite_path, settings.wiki_dir)

