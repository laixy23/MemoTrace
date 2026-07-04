from pathlib import Path

from tracewiki.config import Settings, ensure_dirs
from tracewiki.health_check import review_knowledge_base
from tracewiki.hybrid_retriever import HybridRetriever
from tracewiki.llm import ModelClient
from tracewiki.models import KnowledgeCard, SearchResult, SourceSpan, StagingItem, VectorRecord
from tracewiki.personalization import UserProfile, apply_candidate
from tracewiki.preference_distiller import create_interaction_log, distill_preferences
from tracewiki.reranker import heuristic_rerank
from tracewiki.retriever import LexicalRetriever
from tracewiki.spans import build_text_spans
from tracewiki.storage import KnowledgeStore
from tracewiki.vector_index import hash_embedding
from tracewiki.web_completion import merge_staging_item
from tracewiki.wiki_builder import build_card_from_text
from tracewiki.models import SourceRecord


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        raw_dir=tmp_path / "raw",
        wiki_dir=tmp_path / "wiki",
        staging_dir=tmp_path / "staging",
        sqlite_path=tmp_path / "kb.sqlite",
        openai_base_url="",
        openai_api_key="",
        text_model="none",
        vision_model="none",
        embedding_model="none",
        vector_backend="sqlite",
        rerank_enabled=True,
    )


def test_build_card_keeps_source_path():
    source = SourceRecord(
        source_id="s1",
        path="data/raw/docs/note.md",
        filename="note.md",
        modality="text",
    )
    card = build_card_from_text(source, "# RAG 笔记\nRAG 使用检索增强生成。")
    assert "data/raw/docs/note.md" in card.content
    assert card.evidence[0]["source_path"] == "data/raw/docs/note.md"


def test_retriever_finds_relevant_card():
    card = KnowledgeCard(
        card_id="c1",
        title="RAG",
        summary="检索增强生成",
        tags=["RAG", "知识库"],
        category="concept",
        source_id="s1",
        source_path="raw/rag.md",
        content="RAG 可以让回答基于外部知识库并附带来源。",
        evidence=[{"source_path": "raw/rag.md"}],
    )
    results = LexicalRetriever([card]).search("RAG 来源")
    assert results
    assert results[0].title == "RAG"


def test_retriever_uses_source_spans_for_precise_evidence():
    source = SourceRecord(
        source_id="s1",
        path="raw/long_note.md",
        filename="long_note.md",
        modality="text",
    )
    text = "第一段介绍背景。\n\n第二段说明 SourceSpan 可以提供更细粒度证据回溯。"
    card = build_card_from_text(source, text)
    spans = build_text_spans(source, card, text)
    results = LexicalRetriever([card], spans).search("细粒度证据回溯")
    assert results
    assert results[0].span_id
    assert results[0].locator.startswith("paragraph_or_chunk")


def test_hybrid_retriever_uses_vector_records_when_lexical_misses(tmp_path):
    settings = make_settings(tmp_path)
    client = ModelClient(settings)
    card = KnowledgeCard(
        card_id="c-vector",
        title="Hidden Topic",
        summary="No literal query terms here.",
        tags=[],
        category="concept",
        source_id="s-vector",
        source_path="raw/vector.md",
        content="This card intentionally lacks the search phrase.",
        evidence=[],
    )
    span = SourceSpan(
        span_id="sp-vector",
        source_id="s-vector",
        card_id=card.card_id,
        source_path=card.source_path,
        locator="paragraph_or_chunk:1",
        text="This span is retrieved through an embedding record.",
        span_type="text",
    )
    vector = VectorRecord(
        item_id="span:sp-vector",
        item_type="span",
        text=span.text,
        vector=hash_embedding("semantic retrieval target"),
        metadata={
            "span_id": span.span_id,
            "card_id": card.card_id,
            "source_path": card.source_path,
            "locator": span.locator,
            "span_type": span.span_type,
        },
    )

    results = HybridRetriever([card], [span], [vector], client).search("semantic retrieval target", limit=1)

    assert results
    assert results[0].span_id == "sp-vector"
    assert results[0].evidence[0]["retrieval_method"] == "vector"


def test_heuristic_rerank_promotes_more_relevant_evidence():
    irrelevant = SearchResult(
        card_id="a",
        title="General notes",
        snippet="unrelated background",
        score=0.05,
        source_path="raw/a.md",
        evidence=[{"retrieval_method": "lexical"}],
    )
    relevant = SearchResult(
        card_id="b",
        title="Vector retrieval rerank",
        snippet="vector retrieval uses rerank evidence",
        score=0.0,
        source_path="raw/b.md",
        evidence=[{"retrieval_method": "hybrid"}],
    )

    reranked = heuristic_rerank("vector retrieval rerank", [irrelevant, relevant])

    assert reranked[0].card_id == "b"


def test_web_staging_merges_only_after_confirmation(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    store = KnowledgeStore(settings.sqlite_path, settings.wiki_dir)
    item = StagingItem(
        staging_id="stage-1",
        title="Traceable RAG",
        url="https://example.com/rag",
        summary="A staged web page about traceable retrieval.",
        content="Traceable retrieval connects answers with source evidence.",
    )
    store.add_staging_item(item)

    assert store.list_cards() == []

    card = merge_staging_item(item.staging_id, settings, store)

    assert card.title
    assert store.list_staging_items()[0].status == "merged"
    assert store.list_cards()[0].card_id == card.card_id


def test_health_check_empty_kb_reports_gap():
    issues = review_knowledge_base([])
    assert issues[0].issue_type == "coverage_gap"


def test_preference_distiller_suggests_code_examples():
    profile = UserProfile(preferred_outputs=["步骤"])
    logs = [
        create_interaction_log("怎么实现", "回答", "technical_explanation", "请给代码", "add_code", True),
        create_interaction_log("模块怎么写", "回答", "technical_explanation", "多给实现", "add_code", True),
    ]
    candidates = distill_preferences(logs, profile)
    assert any(c.field == "preferred_outputs" and c.new_value == "代码示例" for c in candidates)


def test_apply_candidate_updates_profile():
    profile = UserProfile(preferred_outputs=["步骤"])
    logs = [
        create_interaction_log("怎么实现", "回答", "technical_explanation", "请给代码", "add_code", True),
        create_interaction_log("模块怎么写", "回答", "technical_explanation", "多给实现", "add_code", True),
    ]
    candidate = distill_preferences(logs, profile)[0]
    updated = apply_candidate(profile, candidate)
    assert "代码示例" in (updated.preferred_outputs or [])
