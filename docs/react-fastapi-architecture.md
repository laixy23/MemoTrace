# React + FastAPI Architecture

TraceWiki now ships with two runnable interfaces:

- Streamlit MVP: `app.py`
- React + FastAPI workbench: `frontend/` + `backend/`

The React/FastAPI version follows the sibling `ailab-hackathon` structure, but reuses TraceWiki's stronger core modules instead of duplicating logic.

## Backend

Run from the TraceWiki project root:

```powershell
cd C:\Users\UserX\Desktop\AILab\tracewiki
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Main API routes:

- `GET /health`
- `POST /api/documents/upload`
- `GET /api/wiki/cards`
- `POST /api/qa/ask`
- `GET /api/health/review`
- `GET /api/logs/system`
- `GET /api/preferences/profile`
- `POST /api/preferences/feedback`
- `POST /api/preferences/distill`
- `GET /api/preferences/candidates`
- `POST /api/preferences/candidates/{id}/accept`
- `GET /api/preferences/memories`
- `GET /api/preferences/memories/search`
- `POST /api/preferences/memories`
- `PATCH /api/preferences/memories/{id}`
- `DELETE /api/preferences/memories/{id}`
- `GET /api/preferences/skill`
- `POST /api/preferences/skill/distill`
- `POST /api/generate/{kind}`

## Frontend

```powershell
cd C:\Users\UserX\Desktop\AILab\tracewiki\frontend
npm install
npm run dev
```

Default frontend URL:

```text
http://127.0.0.1:5174
```

If the backend address changes, set:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Core Alignment

The frontend is aligned with these TraceWiki capabilities:

- upload and ingest files
- inspect Wiki Cards
- ask questions with SourceSpan evidence
- show a Mermaid evidence work graph
- run knowledge health review
- save feedback, inspect long-term memories, and distill stable preference Skills
- inspect system operation logs
- generate notes, reports, PPT outlines, and mindmaps
