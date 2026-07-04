from __future__ import annotations

import re

from .image_understanding import ImageUnderstanding
from .models import KnowledgeCard, SourceRecord, SourceSpan
from .wiki_builder import stable_id


def build_text_spans(
    source: SourceRecord,
    card: KnowledgeCard,
    text: str,
    max_chars: int = 700,
    overlap: int = 80,
) -> list[SourceSpan]:
    pieces = split_source_text(text, max_chars=max_chars, overlap=overlap)
    return [
        SourceSpan(
            span_id=stable_id(f"{source.source_id}|{card.card_id}|{index}|{piece}"),
            source_id=source.source_id,
            card_id=card.card_id,
            source_path=source.path,
            locator=f"paragraph_or_chunk_{index + 1}",
            text=piece,
            span_type=source.modality,
        )
        for index, piece in enumerate(pieces)
        if piece.strip()
    ]


def build_image_spans(
    source: SourceRecord,
    card: KnowledgeCard,
    info: ImageUnderstanding,
) -> list[SourceSpan]:
    spans = []
    if info.ocr_text.strip():
        spans.append(
            SourceSpan(
                span_id=stable_id(f"{source.source_id}|{card.card_id}|ocr|{info.ocr_text}"),
                source_id=source.source_id,
                card_id=card.card_id,
                source_path=source.path,
                locator="image_ocr_text",
                text=info.ocr_text,
                span_type="image_ocr",
            )
        )
    if info.visual_summary.strip():
        spans.append(
            SourceSpan(
                span_id=stable_id(f"{source.source_id}|{card.card_id}|vlm|{info.visual_summary}"),
                source_id=source.source_id,
                card_id=card.card_id,
                source_path=source.path,
                locator="image_visual_summary",
                text=info.visual_summary,
                span_type="image_vlm",
            )
        )
    for index, point in enumerate(info.key_points, start=1):
        spans.append(
            SourceSpan(
                span_id=stable_id(f"{source.source_id}|{card.card_id}|point|{index}|{point}"),
                source_id=source.source_id,
                card_id=card.card_id,
                source_path=source.path,
                locator=f"image_key_point_{index}",
                text=point,
                span_type="image_key_point",
            )
        )
    return spans


def split_source_text(text: str, max_chars: int = 700, overlap: int = 80) -> list[str]:
    text = text.strip()
    if not text:
        return []

    paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            step = max(1, max_chars - overlap)
            while start < len(paragraph):
                chunks.append(paragraph[start : start + max_chars].strip())
                start += step
            continue

        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)
    return chunks
