from __future__ import annotations

import re
from pathlib import Path

from .models import KnowledgeCard, SystemLog

LINK_SECTION = "## Wiki Links"


def render_index_page(cards: list[KnowledgeCard], wiki_dir: Path) -> Path:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[KnowledgeCard]] = {}
    for card in sorted(cards, key=lambda item: (item.category, item.title.lower())):
        grouped.setdefault(card.category or "uncategorized", []).append(card)

    lines = [
        "# TraceWiki Index",
        "",
        "This page is regenerated from the current Wiki cards. Use it as the first stop before reading individual pages.",
        "",
    ]
    if not cards:
        lines.append("_No Wiki cards yet._")
    for category, items in grouped.items():
        lines.extend([f"## {category}", ""])
        for card in items:
            tags = ", ".join(card.tags) if card.tags else "untagged"
            lines.append(f"- {wiki_link(card)} - {card.summary}")
            lines.append(f"  - Tags: {tags}")
            lines.append(f"  - Source: `{card.source_path}`")
        lines.append("")

    path = wiki_dir / "index.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def render_log_page(logs: list[SystemLog], wiki_dir: Path) -> Path:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# TraceWiki Log",
        "",
        "Chronological activity log mirrored from the system event table.",
        "",
    ]
    if not logs:
        lines.append("_No events yet._")
    for event in logs:
        lines.append(f"- {event.created_at} `{event.action_type}` - {event.summary}")
    path = wiki_dir / "log.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def enrich_card_with_links(card: KnowledgeCard, existing_cards: list[KnowledgeCard], limit: int = 5) -> KnowledgeCard:
    related = find_related_cards(card, existing_cards, limit=limit)
    if not related:
        return card
    base = strip_link_section(card.content)
    lines = [base.rstrip(), "", LINK_SECTION, ""]
    for related_card in related:
        shared = sorted(set(normalized_tags(card)) & set(normalized_tags(related_card)))
        reason = f"shared tags: {', '.join(shared)}" if shared else "related title or category"
        lines.append(f"- {wiki_link(related_card)} - {reason}")
    card.content = "\n".join(lines).rstrip() + "\n"
    return card


def refresh_wiki_navigation(cards: list[KnowledgeCard], logs: list[SystemLog], wiki_dir: Path) -> None:
    render_index_page(cards, wiki_dir)
    render_log_page(logs, wiki_dir)


def find_related_cards(card: KnowledgeCard, existing_cards: list[KnowledgeCard], limit: int = 5) -> list[KnowledgeCard]:
    scored: list[tuple[int, KnowledgeCard]] = []
    card_tags = set(normalized_tags(card))
    title_terms = set(tokenize(card.title + " " + card.summary))
    for candidate in existing_cards:
        if candidate.card_id == card.card_id:
            continue
        score = 0
        score += 3 * len(card_tags & set(normalized_tags(candidate)))
        score += len(title_terms & set(tokenize(candidate.title + " " + candidate.summary)))
        if candidate.category and candidate.category == card.category:
            score += 1
        if score > 0:
            scored.append((score, candidate))
    scored.sort(key=lambda item: (-item[0], item[1].title.lower()))
    return [candidate for _, candidate in scored[:limit]]


def wiki_link(card: KnowledgeCard) -> str:
    return f"[[{wiki_page_name(card)}|{card.title}]]"


def wiki_page_name(card: KnowledgeCard) -> str:
    return Path(card.filename).stem


def strip_link_section(content: str) -> str:
    index = content.find(LINK_SECTION)
    if index < 0:
        return content
    return content[:index].rstrip()


def normalized_tags(card: KnowledgeCard) -> list[str]:
    return [tag.strip().lower() for tag in card.tags if tag.strip()]


def tokenize(text: str) -> list[str]:
    normalized = "".join(ch.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff" else " " for ch in text)
    return [part for part in normalized.split() if part]


def extract_wikilink_targets(content: str) -> list[str]:
    targets = []
    for raw in re.findall(r"\[\[([^\]]+)\]\]", content):
        target = raw.split("|", 1)[0].strip()
        if target:
            targets.append(target)
    return targets
