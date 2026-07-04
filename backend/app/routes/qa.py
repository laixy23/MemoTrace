from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas import AskRequest, AskResponse, EvidenceResult
from backend.app.services import get_settings, get_store
from tracewiki.evidence_graph import build_evidence_graph, result_table
from tracewiki.llm import ModelClient
from tracewiki.personalization import load_profile
from tracewiki.qa import answer_question
from tracewiki.retriever import LexicalRetriever
from tracewiki.system_log import record_event

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
    record_event(
        store,
        "question_received",
        "Received user question",
        {"question": question, "card_count": len(cards), "span_count": len(spans)},
    )
    results = LexicalRetriever(cards, spans).search(question, limit=payload.top_k)
    record_event(
        store,
        "retrieval_completed",
        f"Retrieved {len(results)} evidence items",
        {"result_titles": [item.title for item in results]},
    )
    answer = answer_question(question, results, profile, ModelClient(settings))
    record_event(
        store,
        "answer_generated",
        "Generated source-grounded answer",
        {"claim_count": len(answer.claims), "answer_length": len(answer.text)},
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

