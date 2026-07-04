from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas import CardInfo, WikiPageInfo
from backend.app.services import get_settings
from backend.app.services import get_store

router = APIRouter(prefix="/wiki", tags=["wiki"])


@router.get("/cards", response_model=list[CardInfo])
def list_cards() -> list[CardInfo]:
    return [CardInfo(**card.__dict__) for card in get_store().list_cards()]


@router.get("/index", response_model=WikiPageInfo)
def get_index_page() -> WikiPageInfo:
    settings = get_settings()
    path = settings.wiki_dir / "index.md"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return WikiPageInfo(filename="index.md", content=content)


@router.get("/log", response_model=WikiPageInfo)
def get_log_page() -> WikiPageInfo:
    settings = get_settings()
    path = settings.wiki_dir / "log.md"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return WikiPageInfo(filename="log.md", content=content)
