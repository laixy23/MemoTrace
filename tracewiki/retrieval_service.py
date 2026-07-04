from __future__ import annotations

from .models import SearchResult
from .retriever import LexicalRetriever
from .storage import KnowledgeStore


class RetrievalService:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    def search(self, question: str, top_k: int = 5) -> list[SearchResult]:
        cards = self.store.list_cards()
        spans = self.store.list_spans()
        return LexicalRetriever(cards, spans).search(question, limit=top_k)
