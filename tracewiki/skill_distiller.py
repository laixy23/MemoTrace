from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .memory import MemoryService
from .models import MemoryItem, utc_now_iso


SKILL_TYPES = {"response_preference", "output_format", "task_habit"}


def distill_user_skill(
    memory_service: MemoryService,
    user_id: str,
    wiki_dir: Path,
    *,
    min_confidence: float = 0.78,
    min_support: int = 2,
) -> dict[str, Any]:
    memories = [
        item
        for item in memory_service.list(user_id=user_id, status="active", limit=200)
        if item.memory_type in SKILL_TYPES
        and item.confidence >= min_confidence
        and item.support_count >= min_support
    ]
    memories = _drop_family_conflicts(memories)
    memories.sort(key=lambda item: (item.support_count, item.confidence, item.updated_at), reverse=True)
    selected = memories[:12]
    if not selected:
        return {"updated": False, "path": "", "content": "", "memory_count": 0}

    path = skill_path(wiki_dir, user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_user_skill(user_id, selected)
    path.write_text(content, encoding="utf-8")
    return {
        "updated": True,
        "path": str(path),
        "content": content,
        "memory_count": len(selected),
    }


def maybe_distill_user_skill(
    memory_service: MemoryService,
    user_id: str,
    wiki_dir: Path,
    *,
    min_confidence: float = 0.78,
    min_support: int = 3,
) -> dict[str, Any]:
    try:
        stable = [
            item
            for item in memory_service.list(user_id=user_id, status="active", limit=200)
            if item.memory_type in SKILL_TYPES
            and item.confidence >= min_confidence
            and item.support_count >= min_support
        ]
    except Exception:
        return {"updated": False, "path": "", "content": "", "memory_count": 0}
    if not stable:
        return {"updated": False, "path": "", "content": "", "memory_count": 0}
    return distill_user_skill(
        memory_service,
        user_id,
        wiki_dir,
        min_confidence=min_confidence,
        min_support=min_support,
    )


def load_user_skill(wiki_dir: Path, user_id: str) -> str:
    path = skill_path(wiki_dir, user_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def skill_path(wiki_dir: Path, user_id: str) -> Path:
    safe_user_id = re.sub(r"[^A-Za-z0-9_-]+", "_", user_id).strip("_") or "default"
    return wiki_dir / "skills" / f"{safe_user_id}_preference_skill.md"


def render_user_skill(user_id: str, memories: list[MemoryItem]) -> str:
    lines = [
        f"# 用户画像 Skill：{user_id}",
        "",
        "## Summary",
        "这是由高置信长期记忆蒸馏出的稳定回答策略。它只影响表达方式、结构和任务习惯，不改变事实判断。",
        "",
        "## Default Answer Strategy",
    ]
    for item in memories:
        lines.append(f"- {item.content}")
    lines.extend(
        [
            "",
            "## Boundaries",
            "- 当前用户明确指令优先于本 Skill。",
            "- 私有事实必须来自已入库证据或用户本轮输入，不能从偏好记忆中推断。",
            "- 低置信、一次性、互相冲突的记忆不会写入本 Skill。",
            "",
            "## Sources",
        ]
    )
    for item in memories:
        lines.append(
            f"- `{item.memory_id}`: {item.memory_type}; confidence={item.confidence:.2f}; "
            f"support={item.support_count}; updated_at={item.updated_at}; source={item.source}"
        )
    lines.append(f"- generated_at: {utc_now_iso()}")
    return "\n".join(lines).strip() + "\n"


def _drop_family_conflicts(memories: list[MemoryItem]) -> list[MemoryItem]:
    by_family: dict[str, list[MemoryItem]] = {}
    for item in memories:
        family = str(item.metadata.get("family", item.memory_type))
        by_family.setdefault(family, []).append(item)

    selected: list[MemoryItem] = []
    for family, items in by_family.items():
        if family in {"length"} and len(items) > 1:
            items.sort(key=lambda item: (item.support_count, item.confidence, item.updated_at), reverse=True)
            selected.append(items[0])
        else:
            selected.extend(items)
    return selected
