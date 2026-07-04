from __future__ import annotations

import json

from .llm import ModelClient
from .models import SearchResult
from .retriever import tokenize


def rerank_results(
    question: str,
    results: list[SearchResult],
    client: ModelClient,
    limit: int = 5,
) -> list[SearchResult]:
    if not results:
        return []
    if client.settings.rerank_enabled and client.enabled:
        reranked = llm_rerank(question, results, client)
        if reranked:
            return reranked[:limit]
    return heuristic_rerank(question, results)[:limit]


def llm_rerank(question: str, results: list[SearchResult], client: ModelClient) -> list[SearchResult]:
    payload = [
        {
            "index": index,
            "title": result.title,
            "snippet": result.snippet[:700],
            "source": result.source_path,
        }
        for index, result in enumerate(results)
    ]
    prompt = (
        "你是 RAG 检索重排序器。请根据用户问题对候选证据排序。"
        "只返回 JSON，例如 {\"order\": [2,0,1], \"reason\": \"...\"}。\n\n"
        f"问题: {question}\n\n候选证据:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        text = client.chat([{"role": "user", "content": prompt}])
        data = parse_json(text)
        order = data.get("order", [])
        if not isinstance(order, list):
            return []
        seen = set()
        ordered = []
        for raw_index in order:
            if isinstance(raw_index, int) and 0 <= raw_index < len(results) and raw_index not in seen:
                seen.add(raw_index)
                result = results[raw_index]
                result.score += 0.2
                ordered.append(result)
        ordered.extend(result for index, result in enumerate(results) if index not in seen)
        return ordered
    except Exception:
        return []


def heuristic_rerank(question: str, results: list[SearchResult]) -> list[SearchResult]:
    query_terms = set(tokenize(question))
    reranked = []
    for result in results:
        snippet_terms = set(tokenize(result.snippet))
        title_terms = set(tokenize(result.title))
        overlap = len(query_terms & snippet_terms)
        title_overlap = len(query_terms & title_terms)
        method_bonus = 0.08 if result.evidence and result.evidence[0].get("retrieval_method") == "hybrid" else 0
        result.score = result.score + overlap * 0.04 + title_overlap * 0.06 + method_bonus
        reranked.append(result)
    return sorted(reranked, key=lambda item: item.score, reverse=True)


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
        return {}
