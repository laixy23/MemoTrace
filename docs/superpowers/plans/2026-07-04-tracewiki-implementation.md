# TraceWiki Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable MVP for a traceable multimodal personal knowledge base assistant.

**Architecture:** Streamlit drives the UI. Focused Python modules handle ingest, parsing, image understanding, Wiki generation, storage, retrieval, QA, health review, completion suggestions, personalization, and artifact generation. The MVP works offline with local heuristics and can use OpenAI-compatible APIs when configured.

**Tech Stack:** Python, Streamlit, SQLite, Markdown, pypdf, python-docx, pandas, Pillow, requests, pytest.

## Global Constraints

- Keep raw files under `data/raw/`.
- Keep generated Wiki cards under `data/wiki/`.
- Preserve source evidence for every generated card.
- Run without API keys.
- Use OpenAI-compatible API settings when present.

---

### Task 1: Project Skeleton

**Files:**
- Create: `README.md`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `AGENTS.md`
- Create: `tracewiki/__init__.py`
- Create: `tracewiki/config.py`

**Interfaces:**
- Produces: `load_settings() -> Settings`
- Produces: `ensure_dirs(settings: Settings) -> None`

- [x] Create package and dependency files.
- [x] Add runtime configuration.
- [x] Add agent rules for raw/wiki/staging.

### Task 2: Storage and Models

**Files:**
- Create: `tracewiki/models.py`
- Create: `tracewiki/storage.py`

**Interfaces:**
- Produces: `SourceRecord`
- Produces: `KnowledgeCard`
- Produces: `KnowledgeStore.upsert_source(source)`
- Produces: `KnowledgeStore.upsert_card(card)`
- Produces: `KnowledgeStore.list_cards()`

- [x] Define source, card, search, claim, and answer dataclasses.
- [x] Create SQLite schema.
- [x] Persist Markdown card files.

### Task 3: Ingest Pipeline

**Files:**
- Create: `tracewiki/parsers.py`
- Create: `tracewiki/image_understanding.py`
- Create: `tracewiki/wiki_builder.py`
- Create: `tracewiki/ingest.py`

**Interfaces:**
- Produces: `ingest_path(path, settings, store) -> KnowledgeCard`
- Produces: `extract_text(path) -> str`
- Produces: `understand_image(path, client) -> ImageUnderstanding`

- [x] Detect source modality.
- [x] Extract text from common document types.
- [x] Add OCR + VLM hooks.
- [x] Render Markdown Wiki cards.

### Task 4: Retrieval and QA

**Files:**
- Create: `tracewiki/retriever.py`
- Create: `tracewiki/qa.py`
- Create: `tracewiki/llm.py`

**Interfaces:**
- Produces: `LexicalRetriever.search(query, limit=5)`
- Produces: `answer_question(question, results, profile, client) -> Answer`
- Produces: `ModelClient.chat(messages, model=None)`
- Produces: `ModelClient.vision(image_path, prompt)`

- [x] Implement local lexical search.
- [x] Add source-grounded answer fallback.
- [x] Add OpenAI-compatible text and vision API support.

### Task 5: Health Review, Completion, Personalization

**Files:**
- Create: `tracewiki/health_check.py`
- Create: `tracewiki/completion.py`
- Create: `tracewiki/personalization.py`

**Interfaces:**
- Produces: `review_knowledge_base(cards) -> list[HealthIssue]`
- Produces: `propose_completion_actions(issues) -> list[CompletionAction]`
- Produces: `load_profile(path) -> UserProfile`
- Produces: `save_profile(path, profile) -> None`

- [x] Detect empty KB, missing sources, thin summaries, and image gaps.
- [x] Recommend web search or user upload.
- [x] Store user response preferences.

### Task 6: UI and Outputs

**Files:**
- Create: `app.py`
- Create: `tracewiki/generators.py`

**Interfaces:**
- Produces: Streamlit tabs for ingest, QA, Wiki, health review, and generation.
- Produces: `generate_learning_note(cards)`
- Produces: `generate_technical_report(cards)`
- Produces: `generate_ppt_outline(cards)`
- Produces: `generate_mindmap(cards)`

- [x] Build Streamlit UI.
- [x] Add generated learning note, report, PPT outline, and Mermaid mindmap.

### Task 7: Verification

**Files:**
- Create: `tests/test_core.py`

**Interfaces:**
- Consumes: core modules from previous tasks.

- [x] Test source preservation.
- [x] Test retrieval.
- [x] Test health review on empty KB.

