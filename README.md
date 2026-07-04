# TraceWiki

TraceWiki is a traceable multimodal personal knowledge base assistant for hackathon-style demos.

It turns files, notes, code, tables, and images into Markdown wiki cards, then supports:

- multimodal ingest with OCR + VLM hooks
- source-backed QA with claim-level evidence
- knowledge health review
- gap-aware completion suggestions
- Mem0-backed long-term user memory with SQLite local fallback
- LangMem memory library for preference extraction and stable Skill distillation
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

For the formal memory path, set `MEM0_API_KEY` and `OPENAI_API_KEY`; TraceWiki will use LangMem as
the memory library and Mem0 as the long-term storage backend. Without `MEM0_API_KEY`,
`TRACEWIKI_MEMORY_BACKEND=auto` falls back to local SQLite storage for development.

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
4. Let the QA loop retrieve memories, log the turn, and extract preference memories.
5. Run knowledge health review.
6. Distill stable high-confidence preferences into a user Skill.
7. Generate a report, PPT outline, or mindmap.
