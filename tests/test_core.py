from pathlib import Path

from tracewiki.config import Settings, ensure_dirs
from tracewiki.health_check import review_knowledge_base
from tracewiki.hybrid_retriever import HybridRetriever
from tracewiki.llm import ModelClient
from tracewiki.memory import MemoryService
from tracewiki.models import KnowledgeCard, MemoryItem, SearchResult, SourceSpan, StagingItem, SystemLog, VectorRecord
from tracewiki.official_memory import (
    LangMemPreferenceExtractor,
    LocalMemoryServiceAdapter,
    Mem0MemoryService,
    ModelClientPreferenceExtractor,
    create_memory_service,
    create_preference_extractor,
)
from tracewiki.personalization import UserProfile, apply_candidate
from tracewiki.preference_distiller import create_interaction_log, distill_preferences
from tracewiki.qa import generate_fallback_answer
from tracewiki.reranker import heuristic_rerank
from tracewiki.retriever import LexicalRetriever
from tracewiki.skill_distiller import distill_user_skill
from tracewiki.spans import build_text_spans
from tracewiki.storage import KnowledgeStore
from tracewiki.vector_index import hash_embedding
from tracewiki.web_completion import merge_staging_item
from tracewiki.wiki_agent import llm_navigation_plan, wiki_guided_results
from tracewiki.wiki_builder import build_card_from_text
from tracewiki.wiki_maintenance import (
    detect_conflicts_with_llm,
    propose_answer_capture,
    propose_page_updates_with_llm,
)
from tracewiki.wiki_organizer import enrich_card_with_links, render_index_page, render_log_page
from tracewiki.models import SourceRecord


class FakeClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    def chat(self, messages, model=None):
        self.calls.append(messages[-1]["content"])
        return self.text


def make_settings(tmp_path: Path, **overrides) -> Settings:
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
        "openai_base_url": "",
        "openai_api_key": "",
        "text_model": "none",
        "vision_model": "none",
        "embedding_model": "none",
        "vector_backend": "sqlite",
        "rerank_enabled": True,
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


def test_wiki_index_page_lists_cards_with_markdown_links(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    card = KnowledgeCard(
        card_id="card-index",
        title="TraceWiki Architecture",
        summary="A wiki-based RAG architecture.",
        tags=["RAG", "Wiki"],
        category="architecture",
        source_id="source-index",
        source_path="raw/arch.md",
        content="# TraceWiki Architecture",
        evidence=[],
    )

    path = render_index_page([card], settings.wiki_dir)

    text = path.read_text(encoding="utf-8")
    assert path.name == "index.md"
    assert "[[TraceWiki_Architecture|TraceWiki Architecture]]" in text
    assert "A wiki-based RAG architecture." in text


def test_wiki_card_gets_related_wikilinks_section():
    card = KnowledgeCard(
        card_id="card-rag",
        title="RAG Pipeline",
        summary="Retrieval with evidence.",
        tags=["RAG", "Evidence"],
        category="concept",
        source_id="s1",
        source_path="raw/rag.md",
        content="# RAG Pipeline\n\nRetrieval with evidence.",
        evidence=[],
    )
    related = KnowledgeCard(
        card_id="card-evidence",
        title="Evidence Graph",
        summary="Tracks citations.",
        tags=["Evidence"],
        category="concept",
        source_id="s2",
        source_path="raw/evidence.md",
        content="# Evidence Graph",
        evidence=[],
    )

    enriched = enrich_card_with_links(card, [related])

    assert "## Wiki Links" in enriched.content
    assert "[[Evidence_Graph|Evidence Graph]]" in enriched.content


def test_llm_wikilinks_override_rule_links_when_available():
    card = KnowledgeCard(
        card_id="card-rag",
        title="RAG Pipeline",
        summary="Retrieval with evidence.",
        tags=["RAG"],
        category="concept",
        source_id="s1",
        source_path="raw/rag.md",
        content="# RAG Pipeline\n\nRetrieval with evidence.",
        evidence=[],
    )
    semantic = KnowledgeCard(
        card_id="card-source",
        title="SourceSpan Evidence",
        summary="Fine-grained traceable snippets.",
        tags=["Traceability"],
        category="evidence",
        source_id="s2",
        source_path="raw/source.md",
        content="# SourceSpan Evidence",
        evidence=[],
    )
    client = FakeClient('{"links":[{"title":"SourceSpan Evidence","reason":"semantic evidence traceability"}]}')

    enriched = enrich_card_with_links(card, [semantic], client=client)

    assert "[[SourceSpan_Evidence|SourceSpan Evidence]]" in enriched.content
    assert "semantic evidence traceability" in enriched.content


def test_llm_index_rendering_uses_model_maintained_outline(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    card = KnowledgeCard(
        card_id="card-index",
        title="TraceWiki Architecture",
        summary="A wiki-based RAG architecture.",
        tags=["RAG"],
        category="architecture",
        source_id="source-index",
        source_path="raw/arch.md",
        content="# TraceWiki Architecture",
        evidence=[],
    )
    client = FakeClient("# TraceWiki Index\n\n## Important\n- [[TraceWiki_Architecture|TraceWiki Architecture]] - curated by LLM")

    path = render_index_page([card], settings.wiki_dir, client=client)

    text = path.read_text(encoding="utf-8")
    assert "curated by LLM" in text


def test_log_page_renders_system_events(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    store = KnowledgeStore(settings.sqlite_path, settings.wiki_dir)
    store.add_system_log(
        SystemLog(
            log_id="log-1",
            action_type="wiki_card_created",
            summary="Created Wiki card",
            payload={"card_id": "c1"},
            created_at="2026-07-04T00:00:00+00:00",
        )
    )

    path = render_log_page(store.list_system_logs(), settings.wiki_dir)

    text = path.read_text(encoding="utf-8")
    assert path.name == "log.md"
    assert "wiki_card_created" in text
    assert "Created Wiki card" in text


def test_llm_log_page_summarizes_maintenance_events(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    log = SystemLog(
        log_id="log-1",
        action_type="wiki_card_created",
        summary="Created Wiki card",
        payload={"card_id": "c1"},
        created_at="2026-07-04T00:00:00+00:00",
    )
    client = FakeClient("# TraceWiki Log\n\n## 2026-07-04\n- Updated [[RAG]] from a new source.")

    path = render_log_page([log], settings.wiki_dir, client=client)

    text = path.read_text(encoding="utf-8")
    assert "Updated [[RAG]]" in text


def test_wiki_guided_results_add_index_and_followed_page(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    architecture = KnowledgeCard(
        card_id="card-arch",
        title="TraceWiki Architecture",
        summary="Links to evidence graph.",
        tags=["RAG"],
        category="architecture",
        source_id="s1",
        source_path="raw/arch.md",
        content="# TraceWiki Architecture\n\nRelated: [[Evidence_Graph|Evidence Graph]]",
        evidence=[],
    )
    evidence = KnowledgeCard(
        card_id="card-evidence",
        title="Evidence Graph",
        summary="Explains traceable citations.",
        tags=["Evidence"],
        category="concept",
        source_id="s2",
        source_path="raw/evidence.md",
        content="# Evidence Graph\n\nClaim-level citations.",
        evidence=[],
    )
    render_index_page([architecture, evidence], settings.wiki_dir)
    initial = [
        SearchResult(
            card_id=architecture.card_id,
            title=architecture.title,
            snippet=architecture.summary,
            score=0.9,
            source_path=architecture.source_path,
            evidence=[{"retrieval_method": "hybrid"}],
        )
    ]

    results = wiki_guided_results("How does evidence work?", [architecture, evidence], initial, settings.wiki_dir)

    locators = [result.locator for result in results]
    assert "wiki_index" in locators
    assert "follow_link" in locators


def test_llm_navigation_plan_selects_pages_and_followups():
    architecture = KnowledgeCard(
        card_id="card-arch",
        title="TraceWiki Architecture",
        summary="Links to evidence graph.",
        tags=["RAG"],
        category="architecture",
        source_id="s1",
        source_path="raw/arch.md",
        content="# TraceWiki Architecture",
        evidence=[],
    )
    evidence = KnowledgeCard(
        card_id="card-evidence",
        title="Evidence Graph",
        summary="Explains traceable citations.",
        tags=["Evidence"],
        category="concept",
        source_id="s2",
        source_path="raw/evidence.md",
        content="# Evidence Graph",
        evidence=[],
    )
    client = FakeClient('{"read_pages":["Evidence Graph"],"follow_links":["TraceWiki_Architecture"],"sufficient":true}')

    plan = llm_navigation_plan("How is evidence traced?", [architecture, evidence], client)

    assert plan["read_pages"] == ["Evidence Graph"]
    assert plan["follow_links"] == ["TraceWiki_Architecture"]
    assert plan["sufficient"] is True


def test_llm_page_update_conflict_and_answer_capture_proposals():
    old = KnowledgeCard(
        card_id="old",
        title="RAG",
        summary="Old summary.",
        tags=["RAG"],
        category="concept",
        source_id="s1",
        source_path="raw/old.md",
        content="# RAG\n\nOld content.",
        evidence=[],
    )
    new = KnowledgeCard(
        card_id="new",
        title="Hybrid Retrieval",
        summary="New evidence.",
        tags=["RAG"],
        category="concept",
        source_id="s2",
        source_path="raw/new.md",
        content="# Hybrid Retrieval\n\nNew content.",
        evidence=[],
    )
    update_client = FakeClient(
        '{"updates":[{"target_title":"RAG","rationale":"merge new hybrid retrieval notes","proposed_content":"# RAG\\n\\nUpdated with hybrid retrieval."}]}'
    )
    conflict_client = FakeClient(
        '{"conflicts":[{"title":"RAG definition conflict","target_title":"RAG","rationale":"definitions disagree","proposed_content":"Review old and new evidence."}]}'
    )
    capture_client = FakeClient(
        '{"capture":true,"title":"FAQ Evidence Tracing","rationale":"useful repeated question","content":"# FAQ Evidence Tracing\\n\\nAnswer summary."}'
    )

    updates = propose_page_updates_with_llm(new, [old], update_client)
    conflicts = detect_conflicts_with_llm([old, new], conflict_client)
    captures = propose_answer_capture("How trace evidence?", "Answer summary.", [old], capture_client)

    assert updates[0].proposal_type == "update_page"
    assert updates[0].target_card_id == "old"
    assert "hybrid retrieval" in updates[0].proposed_content
    assert conflicts[0].proposal_type == "conflict"
    assert captures[0].proposal_type == "answer_capture"


def test_health_check_empty_kb_reports_gap():
    issues = review_knowledge_base([])
    assert issues[0].issue_type == "coverage_gap"


def test_llm_health_review_adds_semantic_issues():
    card = KnowledgeCard(
        card_id="health-1",
        title="RAG",
        summary="Retrieval augmented generation with citations.",
        tags=["RAG"],
        category="concept",
        source_id="s1",
        source_path="raw/rag.md",
        content="# RAG\n\nRetrieval augmented generation.",
        evidence=[{"source_path": "raw/rag.md"}],
    )
    client = FakeClient(
        '{"issues":[{"title":"Missing evaluation plan","severity":"medium","issue_type":"evaluation_gap","reason":"No metrics are described","suggestion":"Add retrieval and answer quality metrics."}]}'
    )

    issues = review_knowledge_base([card], client=client)

    assert any(issue.issue_type == "evaluation_gap" for issue in issues)


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
    service = create_memory_service(make_settings(tmp_path, mem0_api_key="test-key"))
    assert isinstance(service, Mem0MemoryService)


def test_memory_factory_uses_sqlite_fallback_without_mem0_key(tmp_path):
    service = create_memory_service(make_settings(tmp_path))
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
