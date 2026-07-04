from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from backend.app.schemas import CardInfo, SourceInfo, UploadResponse
from backend.app.services import get_settings, get_store
from tracewiki.ingest import ingest_path

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    suffix = Path(file.filename or "upload.txt").suffix
    raw = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    card = ingest_path(tmp_path, get_settings(), get_store())
    return UploadResponse(card=CardInfo(**card.__dict__), message=f"Generated Wiki card: {card.title}")


@router.get("/sources", response_model=list[SourceInfo])
def list_sources() -> list[SourceInfo]:
    return [SourceInfo(**item.__dict__) for item in get_store().list_sources()]

