from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from tracewiki.config import Settings, load_settings
from tracewiki.generation_service import GenerationService
from tracewiki.official_memory import MemoryServiceProtocol, create_memory_service
from tracewiki.retrieval_service import RetrievalService
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


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryServiceProtocol:
    settings = get_settings()
    return create_memory_service(settings)


def get_retrieval_service() -> RetrievalService:
    return RetrievalService(get_store())


def get_generation_service() -> GenerationService:
    settings = get_settings()
    return GenerationService(settings, settings.data_dir / "user_profile.json")
