# TraceWiki

TraceWiki is a traceable multimodal personal knowledge base assistant for hackathon-style demos.

It turns files, notes, code, tables, and images into Markdown wiki cards, then supports:

- multimodal ingest with OCR + VLM hooks
- source-backed QA with claim-level evidence
- hybrid lexical + embedding retrieval with optional FAISS/Chroma scoring
- rerank by LLM when configured, with a local heuristic fallback
- Karpathy-style LLM Wiki organization with `index.md`, `log.md`, and automatic `[[wikilinks]]`
- knowledge health review
- web completion to a staging area, then user-confirmed merge into Wiki
- LangMem preference extraction, Mem0-backed long-term memory, and stable Skill distillation
- preference distillation from interaction history
- note, report, PPT outline, and Mermaid mindmap generation

## Quick Start

```powershell
cd C:\Users\UserX\Desktop\AILab\tracewiki
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

## React + FastAPI Workbench

Backend:

```powershell
cd C:\Users\UserX\Desktop\AILab\tracewiki
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd C:\Users\UserX\Desktop\AILab\tracewiki\frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5174`.

The app works without model API keys using local heuristic fallbacks. To enable real LLM/VLM calls, copy `.env.example` to `.env` and set an OpenAI-compatible endpoint.

Useful model and retrieval settings:

```powershell
OPENAI_API_KEY=...
MEM0_API_KEY=...
TRACEWIKI_MEMORY_BACKEND=auto
TRACEWIKI_MEMORY_EXTRACTOR=langmem
TRACEWIKI_LANGMEM_MODEL=openai:gpt-4.1-mini
TRACEWIKI_TEXT_MODEL=gpt-4.1-mini
TRACEWIKI_VISION_MODEL=gpt-4.1-mini
TRACEWIKI_EMBEDDING_MODEL=text-embedding-3-small
TRACEWIKI_VECTOR_BACKEND=sqlite  # sqlite, faiss, or chroma
TRACEWIKI_RERANK_ENABLED=true
```

`sqlite` works without extra dependencies. To try optional backends, install `faiss-cpu` or `chromadb` and set `TRACEWIKI_VECTOR_BACKEND` accordingly. Web completion searches the web, fetches candidate pages into `/api/completion/staging`, and only merges a page into `data/raw/web` and Wiki cards after confirmation.

For personalization, TraceWiki uses a three-layer memory design: LangMem extracts durable preference candidates from conversations, Mem0 stores and retrieves long-term memories when `MEM0_API_KEY` is configured, and stable high-confidence preferences are distilled into user Skills under `data/wiki/skills/`. In `auto` mode, missing Mem0 credentials fall back to local SQLite memory for development.

## LLM Wiki Layer

TraceWiki keeps a lightweight Wiki navigation layer alongside vector retrieval:

- `data/wiki/index.md` is LLM-maintained when a model is configured, with deterministic category rendering as fallback.
- `data/wiki/log.md` is summarized as a readable maintenance diary by the LLM, with event-list rendering as fallback.
- new cards are enriched with semantic `[[Wiki_Links|Wiki Links]]` from the LLM, with tag/title/category links as fallback.
- QA augments hybrid retrieval with LLM-guided Wiki navigation: choose pages to read, follow links, and record whether evidence is sufficient.
- LLM maintenance proposals are staged for confirmation: old-page updates, conflict reviews, and answer-capture pages.
- accepted answer-capture proposals become Wiki cards with SourceSpan evidence and vector records.

This keeps the project close to Karpathy's LLM Wiki idea while retaining the practical RAG pieces needed for the hackathon demo.

## Project Idea

TraceWiki follows the LLM-Wiki idea: raw sources are preserved, AI-generated wiki pages are editable Markdown, and every answer points back to original evidence.

```text
raw source -> extracted record -> wiki card -> search index -> cited answer
```

## Directory Layout

```text
tracewiki/
  app.py
  tracewiki/
    ingest.py
    parsers.py
    image_understanding.py
    wiki_builder.py
    retriever.py
    qa.py
    health_check.py
    completion.py
    personalization.py
    generators.py
  data/
    raw/
    wiki/
    staging/
    kb.sqlite
  docs/
    technical-solution.md
    roadmap.md
```

## Demo Flow

1. Upload a slide photo, a note, and a code file.
2. Click ingest to generate wiki cards.
3. Ask a question and inspect the evidence chain.
4. Let QA retrieve memories, save interaction feedback, and extract/update long-term preferences.
5. Run knowledge health review.
6. Distill stable high-confidence preferences into a user Skill.
7. Generate a report, PPT outline, or mindmap.
