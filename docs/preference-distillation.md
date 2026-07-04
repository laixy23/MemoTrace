# Preference Distillation Module

## Purpose

This module upgrades personalization from manual settings to an auditable learning loop.

The original manual profile remains available in the sidebar as a fallback. The new module learns from interaction history, but it does not silently rewrite the user profile. It generates preference candidates first, then asks the user to accept or reject them.

## Flow

```text
QA interaction
 -> document evidence retrieval
 -> MemoryService retrieval
 -> answer generation
 -> interaction_logs table
 -> LangMem memory manager
 -> Mem0 memories
 -> stable high-confidence memories
 -> data/wiki/skills/{user_id}_preference_skill.md
 -> future answers adapt style
```

The older `preference_candidates` flow still exists as a user-confirmed profile editor. The default
formal path uses LangMem as the memory library and Mem0 for storage. `TRACEWIKI_MEMORY_BACKEND=auto`
uses Mem0 when `MEM0_API_KEY` is present and SQLite only as a local development fallback.

```text
TRACEWIKI_MEMORY_BACKEND=mem0
TRACEWIKI_MEMORY_EXTRACTOR=langmem
MEM0_API_KEY=...
OPENAI_API_KEY=...
TRACEWIKI_LANGMEM_MODEL=openai:gpt-4.1-mini
```

In `mem0` mode, TraceWiki uses Mem0's HTTP memory API for storage, retrieval, update, and deletion.
In `langmem` mode, TraceWiki uses LangMem's `create_memory_manager` as the memory library layer.
If LangMem or its model is unavailable, extraction falls back to deterministic rules so zero-config
local development does not fail. For explicit offline development, set
`TRACEWIKI_MEMORY_EXTRACTOR=rules`.

## Captured Signals

- accepted or rejected answer
- request for code examples
- request for tables
- request for step-by-step explanation
- request for shorter answer
- request for more detailed answer
- request for PPT-style output
- free-text feedback such as "too vague" or "give implementation path"
- common topics such as RAG, multimodal, memory, Skills, frontend, backend

## Candidate Format

Each candidate includes:

- field to change
- old value
- new value
- evidence from history
- confidence
- status: pending, accepted, or rejected

Example:

```json
{
  "field": "preferred_outputs",
  "old_value": "步骤",
  "new_value": "代码示例",
  "evidence": "最近 2 条交互中，用户 2 次选择或反馈需要“代码示例”。",
  "confidence": 0.75,
  "status": "pending"
}
```

## Why This Is Safer

- The system only learns expression preferences, not facts.
- The user can inspect every proposed memory.
- The user can reject bad candidates.
- The manual profile still works as a direct override.
- Stable Skills include a `Sources` section with memory IDs instead of raw conversation text.
- Stable Skills are auto-refreshed after memory updates once enough high-confidence support exists,
  and can still be triggered manually from the UI/API.

## Implementation Files

- `tracewiki/preference_distiller.py`
- `tracewiki/memory.py`
- `tracewiki/official_memory.py`
- `tracewiki/generation_service.py`
- `tracewiki/retrieval_service.py`
- `tracewiki/skill_distiller.py`
- `tracewiki/personalization.py`
- `tracewiki/storage.py`
- `app.py`
