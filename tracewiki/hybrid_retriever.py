from __future__ import annotations

from .llm import ModelClient
from .models import KnowledgeCard, SearchResult, SourceSpan, VectorRecord
from .retriever import LexicalRetriever, make_snippet
from .vector_backends import score_vector_records
from .vector_index import embed_query


class HybridRetriever:
    def __init__(
        self,
        cards: list[KnowledgeCard],
        spans: list[SourceSpan],
        vectors: list[VectorRecord],
        client: ModelClient,
    ) -> None:
        self.cards = cards
        self.spans = spans
        self.vectors = vectors
        self.client = client

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        lexical = LexicalRetriever(self.cards, self.spans).search(query, limit=limit * 4)
        vector = self.vector_search(query, limit=limit * 4)
        merged: dict[str, SearchResult] = {}

        for rank, result in enumerate(lexical):
            key = result.span_id or result.card_id
            result.score = result.score * 0.45 + reciprocal_rank(rank)
            merged[key] = result

        for rank, result in enumerate(vector):
            key = result.span_id or result.card_id
            score = result.score * 0.55 + reciprocal_rank(rank)
            if key in merged:
                merged[key].score += score
                merged[key].evidence[0]["retrieval_method"] = "hybrid"
            else:
                result.score = score
                merged[key] = result

        results = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        return results[:limit]

    def vector_search(self, query: str, limit: int) -> list[SearchResult]:
        query_vector = embed_query(query, self.client)
        card_by_id = {card.card_id: card for card in self.cards}
        span_by_id = {span.span_id: span for span in self.spans}
        scored: list[tuple[float, SearchResult]] = []
        for score, record in score_vector_records(query_vector, self.vectors, self.client.settings.vector_backend, limit):
            if record.item_type == "span":
                span_id = str(record.metadata.get("span_id", ""))
                span = span_by_id.get(span_id)
                if not span:
                    continue
                card = card_by_id.get(span.card_id)
                scored.append(
                    (
                        score,
                        SearchResult(
                            card_id=span.card_id,
                            title=card.title if card else span.locator,
                            snippet=make_snippet(span.text, query),
                            score=score,
                            source_path=span.source_path,
                            evidence=[
                                {
                                    "source_path": span.source_path,
                                    "locator": span.locator,
                                    "span_id": span.span_id,
                                    "span_type": span.span_type,
                                    "wiki_card_id": span.card_id,
                                    "text": span.text[:500],
                                    "retrieval_method": "vector",
                                }
                            ],
                            span_id=span.span_id,
                            locator=span.locator,
                        ),
                    )
                )
            elif record.item_type == "card":
                card_id = str(record.metadata.get("card_id", ""))
                card = card_by_id.get(card_id)
                if not card:
                    continue
                scored.append(
                    (
                        score,
                        SearchResult(
                            card_id=card.card_id,
                            title=card.title,
                            snippet=make_snippet(card.content, query),
                            score=score,
                            source_path=card.source_path,
                            evidence=[
                                {
                                    "source_path": card.source_path,
                                    "locator": "wiki_card",
                                    "wiki_card_id": card.card_id,
                                    "retrieval_method": "vector",
                                }
                            ],
                        ),
                    )
                )
        return [item for _, item in scored[:limit]]


def reciprocal_rank(rank: int) -> float:
    return 1.0 / (60.0 + rank)
