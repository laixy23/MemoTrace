from pathlib import Path

from tracewiki.health_check import review_knowledge_base
from tracewiki.models import KnowledgeCard
from tracewiki.personalization import UserProfile, apply_candidate
from tracewiki.preference_distiller import create_interaction_log, distill_preferences
from tracewiki.retriever import LexicalRetriever
from tracewiki.spans import build_text_spans
from tracewiki.wiki_builder import build_card_from_text
from tracewiki.models import SourceRecord


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
