from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .image_understanding import ImageUnderstanding
from .models import KnowledgeCard, SourceRecord


def build_card_from_text(source: SourceRecord, text: str) -> KnowledgeCard:
    title = infer_title(source.filename, text)
    summary = summarize_text(text)
    tags = infer_tags(text)
    category = infer_category(source.modality, text)
    content = render_markdown_card(
        title=title,
        summary=summary,
        tags=tags,
        category=category,
        body=text[:8000],
        source_path=source.path,
        extra_sections={},
    )
    return KnowledgeCard(
        card_id=stable_id(source.path + summary),
        title=title,
        summary=summary,
        tags=tags,
        category=category,
        source_id=source.source_id,
        source_path=source.path,
        content=content,
        evidence=[{"source_path": source.path, "locator": "full_file"}],
    )


def build_card_from_image(source: SourceRecord, info: ImageUnderstanding) -> KnowledgeCard:
    text = "\n".join([info.ocr_text, info.visual_summary, "\n".join(info.key_points)])
    title = infer_title(source.filename, text)
    summary = summarize_text(info.visual_summary + "\n" + info.ocr_text)
    tags = sorted(set(["image", info.image_type] + infer_tags(text)))[:8]
    content = render_markdown_card(
        title=title,
        summary=summary,
        tags=tags,
        category="image",
        body=info.visual_summary,
        source_path=source.path,
        extra_sections={
            "OCR Text": info.ocr_text,
            "Key Points": "\n".join(f"- {item}" for item in info.key_points),
        },
    )
    return KnowledgeCard(
        card_id=stable_id(source.path + summary),
        title=title,
        summary=summary,
        tags=tags,
        category="image",
        source_id=source.source_id,
        source_path=source.path,
        content=content,
        evidence=[
            {
                "source_path": source.path,
                "locator": "image_full",
                "ocr_available": not info.ocr_text.startswith("OCR not available"),
                "vlm_available": not info.visual_summary.startswith("VLM not configured"),
            }
        ],
    )


def render_markdown_card(
    title: str,
    summary: str,
    tags: list[str],
    category: str,
    body: str,
    source_path: str,
    extra_sections: dict[str, str],
) -> str:
    tag_text = ", ".join(tags)
    sections = [
        f"# {title}",
        "",
        "## Summary",
        summary,
        "",
        "## Tags",
        tag_text,
        "",
        "## Category",
        category,
        "",
        "## Knowledge",
        body.strip() or "No extractable text was found.",
    ]
    for heading, content in extra_sections.items():
        sections.extend(["", f"## {heading}", content.strip()])
    sections.extend(["", "## Sources", f"- `{source_path}`"])
    return "\n".join(sections).strip() + "\n"


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def infer_title(filename: str, text: str) -> str:
    for line in text.splitlines():
        clean = line.strip("# \t")
        if 4 <= len(clean) <= 80:
            return clean
    return Path(filename).stem


def summarize_text(text: str, limit: int = 220) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return "No summary could be generated from this source."
    return clean[:limit] + ("..." if len(clean) > limit else "")


def infer_category(modality: str, text: str) -> str:
    lower = text.lower()
    if modality == "code":
        return "code"
    if "rag" in lower or "embedding" in lower or "向量" in lower:
        return "concept"
    if "赛题" in text or "任务" in text:
        return "task"
    return modality


def infer_tags(text: str) -> list[str]:
    keywords = [
        "RAG",
        "OCR",
        "VLM",
        "LLM",
        "Chroma",
        "FAISS",
        "SQLite",
        "知识库",
        "可追溯",
        "个性化",
        "多模态",
        "问答",
        "PPT",
        "代码",
    ]
    lower = text.lower()
    tags = [kw for kw in keywords if kw.lower() in lower or kw in text]
    return tags[:8] or ["knowledge"]

