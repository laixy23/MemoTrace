# TraceWiki Design Spec

## Goal

Build a hackathon-ready personal knowledge base assistant that turns multimodal sources into traceable Markdown wiki cards, then supports source-backed QA, knowledge health review, gap-aware completion suggestions, and personalized response style.

## User Value

Users can upload fragmented study, research, and development materials and get a knowledge base that is readable, searchable, auditable, and useful for generating notes, reports, PPT outlines, and mindmaps.

## Architecture

The app is a Streamlit single-process MVP with focused Python modules. Raw files are copied into `data/raw/`, generated knowledge is stored as Markdown under `data/wiki/`, and metadata is stored in SQLite. Retrieval uses a local lexical search fallback, with a clean path to add vector search later.

## Components

- `app.py`: Streamlit UI.
- `tracewiki/ingest.py`: upload saving and ingest orchestration.
- `tracewiki/parsers.py`: text, PDF, DOCX, spreadsheet, and code extraction.
- `tracewiki/image_understanding.py`: OCR + VLM image pipeline.
- `tracewiki/wiki_builder.py`: Markdown card generation.
- `tracewiki/storage.py`: SQLite and Markdown persistence.
- `tracewiki/retriever.py`: local lexical retrieval.
- `tracewiki/qa.py`: source-grounded answer generation.
- `tracewiki/health_check.py`: knowledge defect detection.
- `tracewiki/completion.py`: web-search vs user-upload recommendations.
- `tracewiki/personalization.py`: user preference memory.
- `tracewiki/generators.py`: notes, reports, PPT outlines, mindmaps.

## Data Flow

```text
upload -> raw file -> parser/OCR/VLM -> KnowledgeCard -> SQLite + Markdown
question -> retriever -> evidence -> answer -> claim-level citations
health review -> issues -> completion actions
```

## Constraints

- Must run without API keys using heuristic fallbacks.
- Must support model APIs through OpenAI-compatible environment variables.
- Must keep raw sources unchanged.
- Must keep generated knowledge human-readable.
- Must make uncertainty and missing evidence visible.

## Success Criteria

- A user can upload files and generate Wiki cards.
- A user can ask a question and see evidence.
- A user can run a health review and get actionable gaps.
- A user can generate at least one report-like artifact.
- The project includes runnable instructions and tests.

