from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas import GenerateResponse
from backend.app.services import get_store
from tracewiki.generators import (
    generate_learning_note,
    generate_mindmap,
    generate_ppt_outline,
    generate_technical_report,
)

router = APIRouter(prefix="/generate", tags=["generation"])


@router.get("/{kind}", response_model=GenerateResponse)
def generate(kind: str) -> GenerateResponse:
    cards = get_store().list_cards()
    if kind == "note":
        content = generate_learning_note(cards)
    elif kind == "report":
        content = generate_technical_report(cards)
    elif kind == "ppt":
        content = generate_ppt_outline(cards)
    elif kind == "mindmap":
        content = generate_mindmap(cards)
    else:
        raise HTTPException(status_code=400, detail="kind must be note, report, ppt, or mindmap")
    return GenerateResponse(kind=kind, content=content)

