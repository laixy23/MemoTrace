from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas import SystemLogInfo
from backend.app.services import get_store

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/system", response_model=list[SystemLogInfo])
def list_system_logs() -> list[SystemLogInfo]:
    return [SystemLogInfo(**log.__dict__) for log in get_store().list_system_logs()]

