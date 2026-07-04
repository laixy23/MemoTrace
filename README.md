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
- user preference memory for response style
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
TRACEWIKI_TEXT_MODEL=gpt-4.1-mini
TRACEWIKI_VISION_MODEL=gpt-4.1-mini
TRACEWIKI_EMBEDDING_MODEL=text-embedding-3-small
TRACEWIKI_VECTOR_BACKEND=sqlite  # sqlite, faiss, or chroma
TRACEWIKI_RERANK_ENABLED=true
```

`sqlite` works without extra dependencies. To try optional backends, install `faiss-cpu` or `chromadb` and set `TRACEWIKI_VECTOR_BACKEND` accordingly. Web completion searches the web, fetches candidate pages into `/api/completion/staging`, and only merges a page into `data/raw/web` and Wiki cards after confirmation.

## LLM Wiki Layer

TraceWiki keeps a lightweight Wiki navigation layer alongside vector retrieval:

- `data/wiki/index.md` is regenerated from current cards and acts as the first page an agent reads.
- `data/wiki/log.md` mirrors system events into a readable Markdown activity log.
- new cards are enriched with `[[Wiki_Links|Wiki Links]]` to related existing cards when tags, titles, or categories overlap.
- QA augments hybrid retrieval with a Wiki-guided read step: include the index page, read matched Wiki cards, then follow explicit links.

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
4. Save interaction feedback and distill response preferences.
5. Run knowledge health review.
6. Generate a report, PPT outline, or mindmap.
