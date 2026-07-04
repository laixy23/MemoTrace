from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas import AskRequest, AskResponse, EvidenceResult
from backend.app.services import get_settings, get_store
from tracewiki.evidence_graph import build_evidence_graph, result_table
from tracewiki.hybrid_retriever import HybridRetriever
from tracewiki.llm import ModelClient
from tracewiki.personalization import load_profile
from tracewiki.qa import answer_question
from tracewiki.reranker import rerank_results
from tracewiki.system_log import record_event
from tracewiki.wiki_agent import wiki_guided_results
from tracewiki.wiki_maintenance import propose_answer_capture

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    store = get_store()
    settings = get_settings()
    profile = load_profile(settings.data_dir / "user_profile.json")
    cards = store.list_cards()
    spans = store.list_spans()
    vectors = store.list_vectors()
    client = ModelClient(settings)
    record_event(
        store,
        "question_received",
        "Received user question",
        {"question": question, "card_count": len(cards), "span_count": len(spans), "vector_count": len(vectors)},
    )
    results = HybridRetriever(cards, spans, vectors, client).search(question, limit=max(payload.top_k * 3, 10))
    results = rerank_results(question, results, client, limit=payload.top_k)
    results = wiki_guided_results(question, cards, results, settings.wiki_dir, limit=max(payload.top_k + 3, 8), client=client)
    record_event(
        store,
        "retrieval_completed",
        f"Retrieved, reranked, and wiki-guided {len(results)} evidence items",
        {
            "result_titles": [item.title for item in results],
            "rerank_enabled": settings.rerank_enabled,
            "wiki_guided": True,
        },
    )
    answer = answer_question(question, results, profile, client)
    proposals = propose_answer_capture(question, answer.text, cards, client)
    for proposal in proposals:
        store.add_wiki_proposal(proposal)
    record_event(
        store,
        "answer_generated",
        "Generated source-grounded answer",
        {
            "claim_count": len(answer.claims),
            "answer_length": len(answer.text),
            "llm_answer_capture_proposals": len(proposals),
        },
        client=client,
    )
    claims = [
        {"text": claim.text, "confidence": claim.confidence, "evidence": claim.evidence}
        for claim in answer.claims
    ]
    return AskResponse(
        answer=answer.text,
        claims=claims,
        graph_mermaid=build_evidence_graph(question, answer),
        evidence=[EvidenceResult(**row) for row in result_table(results)],
    )
