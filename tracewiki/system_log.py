from __future__ import annotations

from typing import Any

from .models import SystemLog
from .storage import KnowledgeStore
from .wiki_builder import stable_id


def record_event(
    store: KnowledgeStore,
    action_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    client=None,
) -> None:
    payload = payload or {}
    seed = f"{action_type}|{summary}|{payload}|{len(store.list_system_logs(limit=500))}"
    store.add_system_log(
        SystemLog(
            log_id=stable_id(seed),
            action_type=action_type,
            summary=summary,
            payload=payload,
        )
    )
    try:
        from .wiki_organizer import render_log_page

        render_log_page(store.list_system_logs(), store.wiki_dir, client=client)
    except Exception:
        pass
