# Preference Distillation Module

## Purpose

This module upgrades personalization from manual settings to an auditable learning loop.

The original manual profile remains available in the sidebar as a fallback. The new module learns from interaction history, but it does not silently rewrite the user profile. It generates preference candidates first, then asks the user to accept or reject them.

## Flow

```text
QA interaction
 -> user feedback
 -> interaction_logs table
 -> preference distiller
 -> preference_candidates table
 -> user confirms
 -> user_profile.json
 -> future answers adapt style
```

## Captured Signals

- accepted or rejected answer
- request for code examples
- request for tables
- request for step-by-step explanation
- request for shorter answer
- request for more detailed answer
- request for PPT-style output
- free-text feedback such as "too vague" or "give implementation path"

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

## Implementation Files

- `tracewiki/preference_distiller.py`
- `tracewiki/personalization.py`
- `tracewiki/storage.py`
- `app.py`

