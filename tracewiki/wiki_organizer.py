from __future__ import annotations

import re
import json
from pathlib import Path

from .llm import json_or_empty
from .models import KnowledgeCard, SystemLog

LINK_SECTION = "## Wiki Links"


def render_index_page(cards: list[KnowledgeCard], wiki_dir: Path, client=None) -> Path:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    llm_text = llm_render_index(cards, client)
    if llm_text:
        path = wiki_dir / "index.md"
        path.write_text(llm_text.rstrip() + "\n", encoding="utf-8")
        return path
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


def render_log_page(logs: list[SystemLog], wiki_dir: Path, client=None) -> Path:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    llm_text = llm_render_log(logs, client)
    if llm_text:
        path = wiki_dir / "log.md"
        path.write_text(llm_text.rstrip() + "\n", encoding="utf-8")
        return path
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


def enrich_card_with_links(card: KnowledgeCard, existing_cards: list[KnowledgeCard], limit: int = 5, client=None) -> KnowledgeCard:
    link_items = llm_link_items(card, existing_cards, client, limit=limit)
    if not link_items:
        related = find_related_cards(card, existing_cards, limit=limit)
        link_items = [
            {
                "card": related_card,
                "reason": (
                    "shared tags: " + ", ".join(sorted(set(normalized_tags(card)) & set(normalized_tags(related_card))))
                    if set(normalized_tags(card)) & set(normalized_tags(related_card))
                    else "related title or category"
                ),
            }
            for related_card in related
        ]
    if not link_items:
        return card
    base = strip_link_section(card.content)
    lines = [base.rstrip(), "", LINK_SECTION, ""]
    for item in link_items:
        related_card = item["card"]
        reason = item["reason"]
        lines.append(f"- {wiki_link(related_card)} - {reason}")
    card.content = "\n".join(lines).rstrip() + "\n"
    return card


def refresh_wiki_navigation(cards: list[KnowledgeCard], logs: list[SystemLog], wiki_dir: Path, client=None) -> None:
    render_index_page(cards, wiki_dir, client=client)
    render_log_page(logs, wiki_dir, client=client)


def llm_render_index(cards: list[KnowledgeCard], client) -> str:
    if not getattr(client, "enabled", False) or not cards:
        return ""
    payload = [
        {
            "title": card.title,
            "page": wiki_page_name(card),
            "summary": card.summary,
            "tags": card.tags,
            "category": card.category,
            "source_path": card.source_path,
        }
        for card in cards[:80]
    ]
    prompt = (
        "You maintain a personal LLM Wiki index.md. Create a concise Markdown index with grouped sections, "
        "important pages first, and wikilinks like [[Page_Name|Title]]. Return Markdown only.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        text = client.chat([{"role": "user", "content": prompt}]).strip()
    except Exception:
        return ""
    return text if text.startswith("#") else ""


def llm_render_log(logs: list[SystemLog], client) -> str:
    if not getattr(client, "enabled", False) or not logs:
        return ""
    payload = [
        {
            "created_at": event.created_at,
            "action_type": event.action_type,
            "summary": event.summary,
            "payload": event.payload,
        }
        for event in logs[:80]
    ]
    prompt = (
        "You maintain log.md for a personal LLM Wiki. Summarize these system events as a readable Markdown "
        "maintenance diary grouped by date. Keep concrete page names and actions. Return Markdown only.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        text = client.chat([{"role": "user", "content": prompt}]).strip()
    except Exception:
        return ""
    return text if text.startswith("#") else ""


def llm_link_items(card: KnowledgeCard, existing_cards: list[KnowledgeCard], client, limit: int) -> list[dict]:
    if not getattr(client, "enabled", False) or not existing_cards:
        return []
    candidates = [
        {
            "title": candidate.title,
            "summary": candidate.summary,
            "tags": candidate.tags,
            "category": candidate.category,
            "page": wiki_page_name(candidate),
        }
        for candidate in existing_cards[:40]
        if candidate.card_id != card.card_id
    ]
    prompt = (
        "You maintain semantic wikilinks for an LLM Wiki. Choose the most useful related pages for this new card. "
        "Return JSON only: {\"links\":[{\"title\":\"candidate title\",\"reason\":\"why this link helps\"}]}.\n\n"
        f"New card:\n{json.dumps({'title': card.title, 'summary': card.summary, 'tags': card.tags, 'category': card.category, 'content': card.content[:1500]}, ensure_ascii=False)}\n\n"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=False)}"
    )
    try:
        data = json_or_empty(client.chat([{"role": "user", "content": prompt}]))
    except Exception:
        return []
    by_title = {candidate.title: candidate for candidate in existing_cards}
    items = []
    for raw in data.get("links", [])[:limit] if isinstance(data, dict) else []:
        if not isinstance(raw, dict):
            continue
        target = by_title.get(str(raw.get("title", "")))
        if target and target.card_id != card.card_id:
            items.append({"card": target, "reason": str(raw.get("reason", "semantic relation")).strip()})
    return items


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
