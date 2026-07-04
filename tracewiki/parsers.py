from __future__ import annotations

import mimetypes
from pathlib import Path


TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
TABLE_SUFFIXES = {".csv", ".xlsx", ".xls"}
DOC_SUFFIXES = {".pdf", ".docx"}


def detect_modality(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in TABLE_SUFFIXES:
        return "table"
    if suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cpp", ".c", ".h"}:
        return "code"
    if suffix in DOC_SUFFIXES:
        return "document"
    return "text"


def guess_mime(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in {".xlsx", ".xls"}:
        return _extract_excel(path)
    return ""


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return "PDF parser is not installed. Install pypdf to extract this file."
    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"[Page {index}]\n{text}")
    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    try:
        import docx
    except Exception:
        return "DOCX parser is not installed. Install python-docx to extract this file."
    doc = docx.Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_excel(path: Path) -> str:
    try:
        import pandas as pd
    except Exception:
        return "Excel parser is not installed. Install pandas and openpyxl to extract this file."
    sheets = pd.read_excel(path, sheet_name=None)
    parts = []
    for name, frame in sheets.items():
        parts.append(f"[Sheet: {name}]\n{frame.head(80).to_markdown(index=False)}")
    return "\n\n".join(parts)

