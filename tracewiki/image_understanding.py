from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .llm import ModelClient


@dataclass
class ImageUnderstanding:
    ocr_text: str
    visual_summary: str
    key_points: list[str]
    image_type: str


def understand_image(path: Path, client: ModelClient) -> ImageUnderstanding:
    ocr_text = run_ocr(path)
    visual_summary = run_vlm(path, client)
    key_points = extract_key_points(ocr_text + "\n" + visual_summary)
    return ImageUnderstanding(
        ocr_text=ocr_text,
        visual_summary=visual_summary,
        key_points=key_points,
        image_type=guess_image_type(ocr_text, visual_summary),
    )


def run_ocr(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(path), lang="chi_sim+eng").strip()
    except Exception:
        return (
            "OCR not available locally. Configure PaddleOCR, Tesseract, or a model API "
            f"to extract exact text from {path.name}."
        )


def run_vlm(path: Path, client: ModelClient) -> str:
    prompt = (
        "Analyze this image as a personal knowledge-base source. "
        "Describe the image type, visible structure, important text, chart/table/layout "
        "meaning, and knowledge points. Return concise Chinese Markdown."
    )
    response = client.vision(path, prompt)
    if response:
        return response
    return (
        f"VLM not configured. The file {path.name} was stored as an image source. "
        "After setting a vision model API key, regenerate this card for visual understanding."
    )


def extract_key_points(text: str) -> list[str]:
    candidates = []
    for line in text.splitlines():
        clean = line.strip(" -#\t")
        if len(clean) >= 6:
            candidates.append(clean[:120])
    return candidates[:8]


def guess_image_type(ocr_text: str, summary: str) -> str:
    text = (ocr_text + "\n" + summary).lower()
    if "ppt" in text or "slide" in text or "赛题" in text:
        return "slide_photo"
    if "table" in text or "表格" in text:
        return "table_image"
    if "chart" in text or "图表" in text:
        return "chart"
    return "image"

