from __future__ import annotations

import math
import re
from collections import Counter

from .models import KnowledgeCard, SearchResult, SourceSpan


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class LexicalRetriever:
    def __init__(self, cards: list[KnowledgeCard], spans: list[SourceSpan] | None = None) -> None:
        self.cards = cards
        self.spans = spans or []

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query_tokens = Counter(tokenize(query))
        if not query_tokens:
            return []
        scored = []
        card_by_id = {card.card_id: card for card in self.cards}

        for span in self.spans:
            score = cosine(query_tokens, Counter(tokenize(span.text)))
            if score > 0:
                card = card_by_id.get(span.card_id)
                scored.append(
                    (
                        score + 0.05,
                        SearchResult(
                            card_id=span.card_id,
                            title=card.title if card else span.locator,
                            snippet=make_snippet(span.text, query),
                            score=score + 0.05,
                            source_path=span.source_path,
                            evidence=[
                                {
                                    "source_path": span.source_path,
                                    "locator": span.locator,
                                    "span_id": span.span_id,
                                    "span_type": span.span_type,
                                    "wiki_card_id": span.card_id,
                                    "text": span.text[:500],
                                }
                            ],
                            span_id=span.span_id,
                            locator=span.locator,
                        ),
                    )
                )

        for card in self.cards:
            body = " ".join([card.title, card.summary, " ".join(card.tags), card.content])
            score = cosine(query_tokens, Counter(tokenize(body)))
            if score > 0:
                scored.append(
                    (
                        score,
                        SearchResult(
                            card_id=card.card_id,
                            title=card.title,
                            snippet=make_snippet(card.content, query),
                            score=score,
                            source_path=card.source_path,
                            evidence=card.evidence,
                        ),
                    )
                )
        scored.sort(key=lambda item: item[0], reverse=True)
        return dedupe_results([result for _, result in scored], limit=limit)


def dedupe_results(results: list[SearchResult], limit: int) -> list[SearchResult]:
    seen = set()
    deduped = []
    for result in results:
        key = result.span_id or result.card_id
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
        if len(deduped) >= limit:
            break
    return deduped


def cosine(left: Counter[str], right: Counter[str]) -> float:
    shared = set(left) & set(right)
    dot = sum(left[t] * right[t] for t in shared)
    left_norm = math.sqrt(sum(v * v for v in left.values()))
    right_norm = math.sqrt(sum(v * v for v in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def make_snippet(content: str, query: str, limit: int = 360) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    query_tokens = set(tokenize(query))
    best = ""
    best_score = -1
    for line in lines:
        score = len(query_tokens & set(tokenize(line)))
        if score > best_score:
            best = line
            best_score = score
    if not best:
        best = " ".join(lines[:4])
    return best[:limit] + ("..." if len(best) > limit else "")
