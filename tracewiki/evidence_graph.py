from __future__ import annotations

import re

from .models import Answer, SearchResult


def build_evidence_graph(question: str, answer: Answer) -> str:
    lines = [
        "flowchart LR",
        f'  Q["Question: {escape_label(question, 42)}"]',
        '  A["Answer"]',
        "  Q --> A",
    ]
    for index, result in enumerate(answer.used_results[:5], start=1):
        evidence_id = f"E{index}"
        card_id = f"C{index}"
        source_id = f"S{index}"
        lines.append(f'  {evidence_id}["Evidence: {escape_label(result.snippet, 52)}"]')
        lines.append(f'  {card_id}["WikiCard: {escape_label(result.title, 36)}"]')
        lines.append(f'  {source_id}["Source: {escape_label(result.source_path, 42)}"]')
        lines.append(f"  Q --> {evidence_id}")
        lines.append(f"  {evidence_id} --> {card_id}")
        lines.append(f"  {card_id} --> {source_id}")
        lines.append(f"  {evidence_id} --> A")
    return "\n".join(lines)


def result_table(results: list[SearchResult]) -> list[dict[str, str | float]]:
    rows = []
    for result in results:
        rows.append(
            {
                "title": result.title,
                "score": round(result.score, 4),
                "locator": result.locator or "wiki_card",
                "source": result.source_path,
                "snippet": result.snippet,
            }
        )
    return rows


def escape_label(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace('"', "'").replace("[", "(").replace("]", ")")
    if len(value) > limit:
        return value[: limit - 3] + "..."
    return value
