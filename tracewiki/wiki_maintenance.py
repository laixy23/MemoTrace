from __future__ import annotations

import json

from .llm import json_or_empty
from .models import KnowledgeCard, WikiMaintenanceProposal
from .wiki_builder import stable_id


def propose_page_updates_with_llm(
    new_card: KnowledgeCard,
    existing_cards: list[KnowledgeCard],
    client,
    limit: int = 5,
) -> list[WikiMaintenanceProposal]:
    if not getattr(client, "enabled", False) or not existing_cards:
        return []
    payload = {
        "new_card": card_digest(new_card),
        "existing_cards": [card_digest(card) for card in existing_cards[:20]],
    }
    prompt = (
        "You maintain a Markdown LLM Wiki. Decide whether the new card should update existing pages. "
        "Return JSON only: {\"updates\":[{\"target_title\":\"...\",\"rationale\":\"...\",\"proposed_content\":\"full markdown\"}]}. "
        "Prefer updating an existing page when the new card expands or corrects it; return [] if no update is needed.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    data = safe_llm_json(client, prompt)
    by_title = {card.title: card for card in existing_cards}
    proposals = []
    for item in data.get("updates", [])[:limit]:
        if not isinstance(item, dict):
            continue
        target = by_title.get(str(item.get("target_title", "")))
        if not target:
            continue
        content = str(item.get("proposed_content", "")).strip()
        if not content:
            continue
        rationale = str(item.get("rationale", "LLM proposed page update")).strip()
        proposals.append(
            WikiMaintenanceProposal(
                proposal_id=stable_id("update_page|" + target.card_id + "|" + content[:200]),
                proposal_type="update_page",
                title=f"Update {target.title}",
                rationale=rationale,
                proposed_content=content,
                target_card_id=target.card_id,
            )
        )
    return proposals


def detect_conflicts_with_llm(
    cards: list[KnowledgeCard],
    client,
    limit: int = 5,
) -> list[WikiMaintenanceProposal]:
    if not getattr(client, "enabled", False) or len(cards) < 2:
        return []
    prompt = (
        "You are auditing a personal Markdown Wiki. Detect factual conflicts, stale claims, or duplicate pages. "
        "Return JSON only: {\"conflicts\":[{\"title\":\"...\",\"target_title\":\"...\",\"rationale\":\"...\",\"proposed_content\":\"review note\"}]}. "
        "Use proposed_content as a Markdown review note with evidence to inspect.\n\n"
        f"{json.dumps([card_digest(card) for card in cards[:30]], ensure_ascii=False)}"
    )
    data = safe_llm_json(client, prompt)
    by_title = {card.title: card for card in cards}
    proposals = []
    for item in data.get("conflicts", [])[:limit]:
        if not isinstance(item, dict):
            continue
        target = by_title.get(str(item.get("target_title", "")))
        content = str(item.get("proposed_content", "")).strip()
        title = str(item.get("title", "Wiki conflict review")).strip()
        rationale = str(item.get("rationale", "LLM detected a possible knowledge conflict")).strip()
        if not content:
            continue
        proposals.append(
            WikiMaintenanceProposal(
                proposal_id=stable_id("conflict|" + title + "|" + content[:200]),
                proposal_type="conflict",
                title=title,
                rationale=rationale,
                proposed_content=content,
                target_card_id=target.card_id if target else "",
            )
        )
    return proposals


def propose_answer_capture(
    question: str,
    answer_text: str,
    cards: list[KnowledgeCard],
    client,
) -> list[WikiMaintenanceProposal]:
    if not getattr(client, "enabled", False) or not answer_text.strip():
        return []
    payload = {
        "question": question,
        "answer": answer_text[:3000],
        "nearby_cards": [card_digest(card) for card in cards[:10]],
    }
    prompt = (
        "You maintain an LLM Wiki. Decide whether this Q&A should be captured as a new FAQ or page update. "
        "Return JSON only: {\"capture\": true/false, \"title\":\"...\", \"rationale\":\"...\", \"content\":\"full markdown\"}. "
        "Return capture=false for routine or low-value questions.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    data = safe_llm_json(client, prompt)
    if not data.get("capture"):
        return []
    title = str(data.get("title", "Captured Answer")).strip()
    content = str(data.get("content", "")).strip()
    rationale = str(data.get("rationale", "LLM proposed capturing this answer")).strip()
    if not content:
        return []
    return [
        WikiMaintenanceProposal(
            proposal_id=stable_id("answer_capture|" + question + "|" + content[:200]),
            proposal_type="answer_capture",
            title=title,
            rationale=rationale,
            proposed_content=content,
        )
    ]


def safe_llm_json(client, prompt: str) -> dict:
    try:
        text = client.chat([{"role": "user", "content": prompt}])
    except Exception:
        return {}
    parsed = json_or_empty(text)
    return parsed if isinstance(parsed, dict) else {}


def card_digest(card: KnowledgeCard) -> dict:
    return {
        "card_id": card.card_id,
        "title": card.title,
        "summary": card.summary,
        "tags": card.tags,
        "category": card.category,
        "source_path": card.source_path,
        "content_excerpt": card.content[:1500],
    }
