from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas import CardInfo, StagingItemInfo, WebCompletionRequest
from backend.app.services import get_settings, get_store
from tracewiki.web_completion import merge_staging_item, web_search_to_staging

router = APIRouter(prefix="/completion", tags=["completion"])


@router.post("/web", response_model=list[StagingItemInfo])
def web_completion(payload: WebCompletionRequest) -> list[StagingItemInfo]:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query cannot be empty")
    items = web_search_to_staging(query, get_settings(), get_store(), limit=payload.limit)
    return [StagingItemInfo(**item.__dict__) for item in items]


@router.get("/staging", response_model=list[StagingItemInfo])
def list_staging() -> list[StagingItemInfo]:
    return [StagingItemInfo(**item.__dict__) for item in get_store().list_staging_items(status="pending")]


@router.post("/staging/{staging_id}/merge", response_model=CardInfo)
def merge_staging(staging_id: str) -> CardInfo:
    try:
        card = merge_staging_item(staging_id, get_settings(), get_store())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CardInfo(**card.__dict__)
