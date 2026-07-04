from __future__ import annotations

import hashlib
import math

from .llm import ModelClient
from .models import KnowledgeCard, SourceSpan, VectorRecord


HASH_DIMS = 384


def build_vector_records(
    card: KnowledgeCard,
    spans: list[SourceSpan],
    client: ModelClient,
) -> list[VectorRecord]:
    items: list[tuple[str, str, str, dict]] = [
        (
            f"card:{card.card_id}",
            "card",
            " ".join([card.title, card.summary, " ".join(card.tags), card.content[:3000]]),
            {
                "card_id": card.card_id,
                "title": card.title,
                "source_path": card.source_path,
            },
        )
    ]
    for span in spans:
        items.append(
            (
                f"span:{span.span_id}",
                "span",
                span.text,
                {
                    "span_id": span.span_id,
                    "card_id": span.card_id,
                    "source_path": span.source_path,
                    "locator": span.locator,
                    "span_type": span.span_type,
                },
            )
        )
    texts = [item[2] for item in items]
    vectors = embed_texts(texts, client)
    return [
        VectorRecord(
            item_id=item_id,
            item_type=item_type,
            text=text,
            vector=vector,
            metadata=metadata,
        )
        for (item_id, item_type, text, metadata), vector in zip(items, vectors)
    ]


def embed_texts(texts: list[str], client: ModelClient) -> list[list[float]]:
    if client.enabled:
        try:
            vectors = client.embed(texts)
            if vectors:
                return [normalize(vector) for vector in vectors]
        except Exception:
            pass
    return [hash_embedding(text) for text in texts]


def embed_query(text: str, client: ModelClient) -> list[float]:
    return embed_texts([text], client)[0]


def hash_embedding(text: str, dims: int = HASH_DIMS) -> list[float]:
    values = [0.0] * dims
    tokens = tokenize_for_hash(text)
    for token in tokens:
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        values[index] += sign
    return normalize(values)


def tokenize_for_hash(text: str) -> list[str]:
    compact = "".join(ch.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff" else " " for ch in text)
    words = [item for item in compact.split() if item]
    chars = [ch for ch in compact if "\u4e00" <= ch <= "\u9fff"]
    bigrams = ["".join(chars[index : index + 2]) for index in range(max(0, len(chars) - 1))]
    return words + bigrams


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def vector_cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
