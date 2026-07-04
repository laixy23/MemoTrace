from __future__ import annotations

from pathlib import Path

from .models import KnowledgeCard, SearchResult
from .retriever import make_snippet
from .wiki_organizer import extract_wikilink_targets, tokenize, wiki_page_name


def wiki_guided_results(
    question: str,
    cards: list[KnowledgeCard],
    initial_results: list[SearchResult],
    wiki_dir: Path,
    limit: int = 8,
) -> list[SearchResult]:
    results = list(initial_results)
    index_path = wiki_dir / "index.md"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        results.insert(
            0,
            SearchResult(
                card_id="wiki-index",
                title="TraceWiki Index",
                snippet=make_snippet(index_text, question),
                score=1.0,
                source_path=str(index_path),
                evidence=[{"source_path": str(index_path), "locator": "wiki_index", "retrieval_method": "wiki_read"}],
                locator="wiki_index",
            ),
        )

    page_by_name = {wiki_page_name(card): card for card in cards}
    selected_ids = {result.card_id for result in initial_results}
    for card in select_pages(question, cards, selected_ids):
        if any(result.card_id == card.card_id for result in results):
            continue
        results.append(card_result(card, question, "wiki_read"))

    followed = []
    for result in list(results):
        card = next((item for item in cards if item.card_id == result.card_id), None)
        if not card:
            continue
        for target in extract_wikilink_targets(card.content):
            linked = page_by_name.get(target)
            if not linked:
                continue
            existing = next((item for item in results if item.card_id == linked.card_id), None)
            if existing:
                existing.locator = "follow_link"
                if existing.evidence:
                    existing.evidence[0]["locator"] = "follow_link"
                    existing.evidence[0]["retrieval_method"] = "follow_link"
                selected_ids.add(linked.card_id)
            elif linked.card_id not in selected_ids:
                followed.append(linked)
                selected_ids.add(linked.card_id)

    for card in followed:
        if any(result.card_id == card.card_id for result in results):
            continue
        results.append(card_result(card, question, "follow_link"))

    return results[:limit]


def select_pages(question: str, cards: list[KnowledgeCard], selected_ids: set[str], limit: int = 3) -> list[KnowledgeCard]:
    terms = set(tokenize(question))
    scored: list[tuple[int, KnowledgeCard]] = []
    for card in cards:
        if card.card_id in selected_ids:
            continue
        card_terms = set(tokenize(" ".join([card.title, card.summary, " ".join(card.tags)])))
        score = len(terms & card_terms)
        if score:
            scored.append((score, card))
    scored.sort(key=lambda item: (-item[0], item[1].title.lower()))
    return [card for _, card in scored[:limit]]


def card_result(card: KnowledgeCard, question: str, method: str) -> SearchResult:
    return SearchResult(
        card_id=card.card_id,
        title=card.title,
        snippet=make_snippet(card.content or card.summary, question),
        score=0.75 if method == "wiki_read" else 0.65,
        source_path=card.source_path,
        evidence=[
            {
                "source_path": card.source_path,
                "locator": method,
                "wiki_card_id": card.card_id,
                "retrieval_method": method,
            }
        ],
        locator=method,
    )
