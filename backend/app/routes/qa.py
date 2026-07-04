from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas import AskRequest, AskResponse, EvidenceResult
from backend.app.services import get_memory_service, get_settings, get_store
from tracewiki.evidence_graph import build_evidence_graph, result_table
from tracewiki.hybrid_retriever import HybridRetriever
from tracewiki.llm import ModelClient
from tracewiki.personalization import load_profile
from tracewiki.preference_distiller import create_interaction_log
from tracewiki.qa import answer_question
from tracewiki.reranker import rerank_results
from tracewiki.skill_distiller import load_user_skill, maybe_distill_user_skill
from tracewiki.system_log import record_event
from tracewiki.wiki_agent import wiki_guided_results
from tracewiki.wiki_maintenance import propose_answer_capture

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    user_id = payload.user_id.strip() or "default"

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
        {
            "user_id": user_id,
            "question": question,
            "card_count": len(cards),
            "span_count": len(spans),
            "vector_count": len(vectors),
        },
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
    memory_service = get_memory_service()
    memories = memory_service.search(user_id=user_id, query=question)
    record_event(
        store,
        "memory_retrieval_completed",
        f"Retrieved {len(memories)} user memories",
        {"user_id": user_id, "memory_ids": [item.memory_id for item in memories]},
    )
    answer = answer_question(
        question,
        results,
        profile,
        client,
        memories=memories,
        skill=load_user_skill(settings.wiki_dir, user_id),
    )
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
    interaction = create_interaction_log(
        question=question,
        answer_summary=answer.text[:600],
        answer_type="technical_explanation",
        user_feedback="",
        user_action="auto_logged",
        accepted=True,
    )
    store.add_interaction(interaction)
    memory_updates = memory_service.extract_and_update(
        user_id=user_id,
        question=question,
        answer=answer.text,
    )
    if memory_updates:
        record_event(
            store,
            "memory_updated",
            f"Updated {len(memory_updates)} user memories from this QA turn",
            {"user_id": user_id, "memory_ids": [item.memory_id for item in memory_updates]},
        )
        skill_result = maybe_distill_user_skill(
            memory_service,
            user_id=user_id,
            wiki_dir=settings.wiki_dir,
        )
        if skill_result["updated"]:
            record_event(
                store,
                "preference_skill_auto_distilled",
                f"Auto-distilled {skill_result['memory_count']} stable memories into user skill",
                {"user_id": user_id, "path": skill_result["path"]},
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
        memories=[item.__dict__ for item in memories],
        memory_updates=[item.__dict__ for item in memory_updates],
    )
