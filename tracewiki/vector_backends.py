from __future__ import annotations

import uuid

from .models import VectorRecord
from .vector_index import vector_cosine


def score_vector_records(
    query_vector: list[float],
    records: list[VectorRecord],
    backend: str,
    limit: int,
) -> list[tuple[float, VectorRecord]]:
    backend_name = backend.lower().strip()
    if backend_name == "faiss":
        scored = score_with_faiss(query_vector, records, limit)
        if scored:
            return scored
    if backend_name == "chroma":
        scored = score_with_chroma(query_vector, records, limit)
        if scored:
            return scored
    return score_with_cosine(query_vector, records, limit)


def score_with_cosine(query_vector: list[float], records: list[VectorRecord], limit: int) -> list[tuple[float, VectorRecord]]:
    scored = [(vector_cosine(query_vector, record.vector), record) for record in records]
    scored = [(score, record) for score, record in scored if score > 0]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:limit]


def score_with_faiss(query_vector: list[float], records: list[VectorRecord], limit: int) -> list[tuple[float, VectorRecord]]:
    try:
        import faiss  # type: ignore
        import numpy as np
    except Exception:
        return []
    usable = [record for record in records if len(record.vector) == len(query_vector)]
    if not usable or not query_vector:
        return []
    matrix = np.array([record.vector for record in usable], dtype="float32")
    query = np.array([query_vector], dtype="float32")
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    scores, indices = index.search(query, min(limit, len(usable)))
    return [
        (float(score), usable[int(index)])
        for score, index in zip(scores[0], indices[0])
        if int(index) >= 0 and float(score) > 0
    ]


def score_with_chroma(query_vector: list[float], records: list[VectorRecord], limit: int) -> list[tuple[float, VectorRecord]]:
    try:
        import chromadb  # type: ignore
    except Exception:
        return []
    usable = [record for record in records if len(record.vector) == len(query_vector)]
    if not usable or not query_vector:
        return []
    try:
        client = chromadb.Client()
        collection = client.create_collection(name=f"tracewiki_{uuid.uuid4().hex[:12]}")
        collection.add(
            ids=[record.item_id for record in usable],
            embeddings=[record.vector for record in usable],
            documents=[record.text for record in usable],
        )
        payload = collection.query(query_embeddings=[query_vector], n_results=min(limit, len(usable)))
    except Exception:
        return []
    by_id = {record.item_id: record for record in usable}
    ids = payload.get("ids", [[]])[0]
    distances = payload.get("distances", [[]])[0]
    scored: list[tuple[float, VectorRecord]] = []
    for item_id, distance in zip(ids, distances):
        record = by_id.get(item_id)
        if record:
            scored.append((1.0 / (1.0 + float(distance)), record))
    return scored
