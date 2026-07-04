from __future__ import annotations

import shutil
from pathlib import Path

from .config import Settings
from .image_understanding import understand_image
from .llm import ModelClient
from .models import KnowledgeCard, SourceRecord
from .parsers import detect_modality, extract_text, guess_mime
from .spans import build_image_spans, build_text_spans
from .storage import KnowledgeStore
from .system_log import record_event
from .wiki_builder import build_card_from_image, build_card_from_text, stable_id


def save_upload(source_path: Path, settings: Settings) -> SourceRecord:
    modality = detect_modality(source_path)
    target_dir = {
        "image": settings.raw_dir / "images",
        "table": settings.raw_dir / "tables",
        "code": settings.raw_dir / "code",
        "document": settings.raw_dir / "docs",
    }.get(modality, settings.raw_dir / "docs")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = unique_path(target_dir / source_path.name)
    if source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)
    return SourceRecord(
        source_id=stable_id(str(target_path)),
        path=str(target_path),
        filename=target_path.name,
        modality=modality,
        mime_type=guess_mime(target_path),
    )


def ingest_path(path: Path, settings: Settings, store: KnowledgeStore) -> KnowledgeCard:
    client = ModelClient(settings)
    record_event(store, "upload_received", f"Received source file {path.name}", {"path": str(path)})
    source = save_upload(path, settings)
    store.upsert_source(source)
    record_event(
        store,
        "source_saved",
        f"Saved source as {source.modality}",
        {"source_id": source.source_id, "path": source.path},
    )
    stored_path = Path(source.path)
    if source.modality == "image":
        info = understand_image(stored_path, client)
        card = build_card_from_image(source, info)
        spans = build_image_spans(source, card, info)
    else:
        text = extract_text(stored_path)
        card = build_card_from_text(source, text)
        spans = build_text_spans(source, card, text)
    store.upsert_card(card)
    store.replace_spans_for_card(card.card_id, spans)
    record_event(
        store,
        "wiki_card_created",
        f"Created Wiki card and {len(spans)} evidence spans",
        {"card_id": card.card_id, "title": card.title, "span_count": len(spans)},
    )
    return card


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1
