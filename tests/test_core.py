from pathlib import Path

from tracewiki.config import Settings
from tracewiki.health_check import review_knowledge_base
from tracewiki.memory import MemoryService
from tracewiki.models import KnowledgeCard, MemoryItem, SearchResult
from tracewiki.official_memory import (
    LocalMemoryServiceAdapter,
    Mem0MemoryService,
    ModelClientPreferenceExtractor,
    LangMemPreferenceExtractor,
    create_memory_service,
    create_preference_extractor,
)
from tracewiki.personalization import UserProfile, apply_candidate
from tracewiki.preference_distiller import create_interaction_log, distill_preferences
from tracewiki.qa import generate_fallback_answer
from tracewiki.retriever import LexicalRetriever
from tracewiki.skill_distiller import distill_user_skill
from tracewiki.spans import build_text_spans
from tracewiki.wiki_builder import build_card_from_text
from tracewiki.models import SourceRecord


def make_settings(tmp_path: Path, **overrides):
    values = {
        "data_dir": tmp_path,
        "raw_dir": tmp_path / "raw",
        "wiki_dir": tmp_path / "wiki",
        "staging_dir": tmp_path / "staging",
        "sqlite_path": tmp_path / "kb.sqlite",
        "memory_backend": "auto",
        "memory_extractor": "langmem",
        "mem0_api_key": "",
        "mem0_base_url": "https://api.mem0.ai",
        "langmem_model": "openai:gpt-4.1-mini",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_api_key": "",
        "text_model": "gpt-4.1-mini",
        "vision_model": "gpt-4.1-mini",
    }
    values.update(overrides)
    return Settings(**values)


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


def test_memory_service_core_crud_and_search(tmp_path):
    service = MemoryService(tmp_path / "kb.sqlite")
    memory = service.add(
        user_id="u1",
        memory_type="response_preference",
        content="用户偏好简洁回答，先给结论。",
        confidence=0.8,
        source="test",
    )
    assert service.search("u1", "回答风格")

    updated = service.update(memory.memory_id, content="用户偏好简洁回答，先给结论，避免长篇背景。")
    assert updated is not None
    assert "避免长篇" in updated.content
    assert service.delete(memory.memory_id)
    assert service.list("u1") == []


def test_preference_extraction_updates_memory_and_distills_skill(tmp_path):
    service = MemoryService(tmp_path / "kb.sqlite")
    service.extract_and_update(
        user_id="u1",
        question="以后回答短一点，先给结论，可以用表格对比。",
        answer="好的",
    )
    service.extract_and_update(
        user_id="u1",
        question="请继续短一点，先给结论，用表格。",
        answer="好的",
        feedback="不要太学术化",
        action="make_shorter",
    )

    memories = service.list("u1")
    assert any("先给结论" in item.content and item.support_count >= 2 for item in memories)
    assert any("表格" in item.content for item in memories)

    result = distill_user_skill(service, "u1", tmp_path / "wiki")
    assert result["updated"]
    assert "Default Answer Strategy" in result["content"]
    assert "## Sources" in result["content"]


def test_fallback_answer_uses_memory_format_preferences():
    memories = [
        MemoryItem(
            memory_id="m1",
            user_id="u1",
            memory_type="response_preference",
            content="用户偏好简洁回答，先给结论，避免长篇背景铺垫。",
            confidence=0.9,
            source="test",
        ),
        MemoryItem(
            memory_id="m2",
            user_id="u1",
            memory_type="output_format",
            content="复杂对比或方案权衡时，用户偏好使用表格。",
            confidence=0.9,
            source="test",
        ),
    ]
    results = [
        SearchResult(
            card_id="c1",
            title="TraceWiki",
            snippet="TraceWiki 使用 Wiki 卡片和证据链回答问题。",
            score=0.8,
            source_path="data/wiki/tracewiki.md",
            evidence=[{"source_path": "data/wiki/tracewiki.md"}],
        )
    ]
    text = generate_fallback_answer("TraceWiki 怎么回答？", results, UserProfile(), memories)
    assert text.startswith("结论：")
    assert "| 证据 | 摘要 | 来源 |" in text


def test_memory_factory_prefers_mem0_when_configured(tmp_path):
    settings = make_settings(tmp_path, mem0_api_key="test-key")
    service = create_memory_service(settings)
    assert isinstance(service, Mem0MemoryService)


def test_memory_factory_uses_sqlite_fallback_without_mem0_key(tmp_path):
    settings = make_settings(tmp_path)
    service = create_memory_service(settings)
    assert isinstance(service, LocalMemoryServiceAdapter)


def test_model_extractor_falls_back_to_rules_without_api_key(tmp_path):
    extractor = ModelClientPreferenceExtractor(make_settings(tmp_path, memory_extractor="model"))
    memories = extractor.extract(
        question="以后回答短一点，先给结论，用表格。",
        answer="好的",
    )
    assert memories
    assert extractor.last_source_name == "rule_extractor"


def test_langmem_is_default_memory_library(tmp_path):
    extractor = create_preference_extractor(make_settings(tmp_path))
    assert isinstance(extractor, LangMemPreferenceExtractor)


def test_default_sqlite_path_falls_back_to_rules_without_model_key(tmp_path):
    service = create_memory_service(make_settings(tmp_path))
    updates = service.extract_and_update(
        user_id="u1",
        question="以后回答短一点，先给结论，用表格。",
        answer="好的",
    )
    assert updates
    assert all(item.source == "rule_extractor" for item in updates)


class DummyExtractor:
    source_name = "dummy_extractor"

    def __init__(self, items):
        self.items = items

    def extract(self, *args, **kwargs):
        return self.items


class RecordingMem0Service(Mem0MemoryService):
    def __init__(self, items, existing=None):
        self.extractor = DummyExtractor(items)
        self.existing = existing
        self.added = []
        self.updated = []

    def _find_existing_memory(self, user_id, key, content, memory_type):
        return self.existing if self.existing and self.existing.metadata.get("key") == key else None

    def add(self, user_id, memory_type, content, metadata=None, confidence=0.6, source="manual", memory_id=None, status="active"):
        item = MemoryItem(
            memory_id=memory_id or f"added-{len(self.added)}",
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
            confidence=confidence,
            source=source,
            status=status,
        )
        self.added.append(item)
        return item

    def update(self, memory_id, *, content=None, metadata=None, confidence=None, source=None, status=None, support_delta=0):
        item = MemoryItem(
            memory_id=memory_id,
            user_id="u1",
            memory_type="response_preference",
            content=content or "",
            metadata=metadata or {},
            confidence=confidence or 0.7,
            source=source or "dummy_extractor",
            status=status or "active",
            support_count=int((metadata or {}).get("support_count", 1)),
        )
        self.updated.append(item)
        return item


def test_mem0_extract_and_update_writes_every_extracted_memory():
    service = RecordingMem0Service(
        [
            {
                "key": "length:concise",
                "memory_type": "response_preference",
                "content": "用户偏好简洁回答。",
                "confidence": 0.8,
            },
            {
                "key": "format:table",
                "memory_type": "output_format",
                "content": "用户偏好表格对比。",
                "confidence": 0.82,
            },
        ]
    )
    updates = service.extract_and_update("u1", "问题", "回答")
    assert len(updates) == 2
    assert [item.content for item in service.added] == ["用户偏好简洁回答。", "用户偏好表格对比。"]


def test_mem0_extract_and_update_handles_empty_extraction():
    service = RecordingMem0Service([])
    assert service.extract_and_update("u1", "问题", "回答") == []


def test_mem0_extract_and_update_merges_existing_memory():
    existing = MemoryItem(
        memory_id="m1",
        user_id="u1",
        memory_type="response_preference",
        content="用户偏好简洁回答。",
        metadata={"key": "length:concise", "support_count": 2},
        confidence=0.8,
        source="dummy_extractor",
        support_count=2,
    )
    service = RecordingMem0Service(
        [
            {
                "key": "length:concise",
                "memory_type": "response_preference",
                "content": "用户偏好简洁回答，先给结论。",
                "confidence": 0.84,
            }
        ],
        existing=existing,
    )
    updates = service.extract_and_update("u1", "问题", "回答")
    assert len(updates) == 1
    assert not service.added
    assert service.updated[0].metadata["support_count"] == 3
    assert service.updated[0].confidence > existing.confidence
