from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from backend.app.routes import documents, generation, health, logs, preferences, qa, review, wiki
from backend.app.services import get_memory_service, get_settings, get_store
from tracewiki.config import ensure_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_dirs(settings)
    get_store()
    get_memory_service()
    yield


app = FastAPI(
    title="TraceWiki API",
    description="FastAPI backend for a traceable multimodal personal knowledge base.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router, prefix="/api")
app.include_router(wiki.router, prefix="/api")
app.include_router(qa.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(preferences.router, prefix="/api")
app.include_router(generation.router, prefix="/api")
