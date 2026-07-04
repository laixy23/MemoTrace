from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas import CardInfo
from backend.app.services import get_store

router = APIRouter(prefix="/wiki", tags=["wiki"])


@router.get("/cards", response_model=list[CardInfo])
def list_cards() -> list[CardInfo]:
    return [CardInfo(**card.__dict__) for card in get_store().list_cards()]

