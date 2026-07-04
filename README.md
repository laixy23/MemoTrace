# TraceWiki

TraceWiki is a traceable multimodal personal knowledge base assistant for hackathon-style demos.

It turns files, notes, code, tables, and images into Markdown wiki cards, then supports:

- multimodal ingest with OCR + VLM hooks
- source-backed QA with claim-level evidence
- knowledge health review
- gap-aware completion suggestions
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
