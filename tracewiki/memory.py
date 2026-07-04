from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import MemoryItem, utc_now_iso
from .retriever import cosine, tokenize
from .wiki_builder import stable_id


MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  memory_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  memory_type TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  confidence REAL NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  support_count INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_user_status
ON memories(user_id, status, updated_at);

CREATE INDEX IF NOT EXISTS idx_memories_user_type
ON memories(user_id, memory_type, updated_at);
"""


GLOBAL_MEMORY_TYPES = {"response_preference", "output_format", "task_habit"}

TOPIC_RULES = [
    ("topic:rag", "RAG", ["rag", "检索增强", "知识库"]),
    ("topic:multimodal", "多模态", ["多模态", "ocr", "vlm", "图片", "图像"]),
    ("topic:memory", "长期记忆", ["langmem", "mem0", "记忆", "偏好", "画像"]),
    ("topic:skills", "Skills", ["skill", "skills", "技能", "蒸馏"]),
    ("topic:engineering", "工程落地", ["实现", "落地", "架构", "服务", "接口", "模块"]),
    ("topic:frontend", "前端体验", ["前端", "react", "ui", "页面", "交互"]),
    ("topic:backend", "后端服务", ["fastapi", "sqlite", "api", "数据库", "后端"]),
]


class MemoryService:
    """SQLite-backed long-term memory service with Mem0-like core operations."""

    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(MEMORY_SCHEMA)

    def add(
        self,
        user_id: str,
        memory_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        confidence: float = 0.6,
        source: str = "manual",
        memory_id: str | None = None,
        status: str = "active",
    ) -> MemoryItem:
        metadata = metadata or {}
        confidence = _clamp_confidence(confidence)
        memory_id = memory_id or self._memory_id(user_id, memory_type, content, metadata)
        existing = self.get(memory_id)
        if existing:
            merged_metadata = {**existing.metadata, **metadata}
            merged_metadata["last_observed_at"] = utc_now_iso()
            return self.update(
                memory_id,
                content=content,
                metadata=merged_metadata,
                confidence=max(existing.confidence, confidence),
                source=source,
                status=status,
                support_delta=1,
            ) or existing

        now = utc_now_iso()
        item = MemoryItem(
            memory_id=memory_id,
            user_id=user_id,
            memory_type=memory_type,
            content=content.strip(),
            metadata=metadata,
            confidence=confidence,
            source=source,
            status=status,
            support_count=1,
            created_at=now,
            updated_at=now,
        )
        self._insert_or_replace(item)
        return item

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
    ) -> list[MemoryItem]:
        if limit <= 0:
            return []
        query_tokens = tokenize(query)
        query_counter = _counter(query_tokens)
        scored: list[tuple[float, MemoryItem]] = []

        for item in self.list(user_id=user_id, memory_type=memory_type, status="active", limit=200):
            searchable = " ".join([item.content, _metadata_search_text(item.metadata)])
            lexical_score = cosine(query_counter, _counter(tokenize(searchable))) if query_tokens else 0.0
            global_boost = 0.12 if item.memory_type in GLOBAL_MEMORY_TYPES else 0.0
            support_boost = min(item.support_count, 5) * 0.02
            confidence_boost = item.confidence * 0.06
            topic_boost = 0.05 if lexical_score > 0 and item.memory_type == "topic_interest" else 0.0
            score = lexical_score + global_boost + support_boost + confidence_boost + topic_boost
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda pair: (pair[0], pair[1].updated_at), reverse=True)
        return [item for _, item in scored[:limit]]

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        confidence: float | None = None,
        source: str | None = None,
        status: str | None = None,
        support_delta: int = 0,
    ) -> MemoryItem | None:
        item = self.get(memory_id)
        if not item:
            return None
        updated = MemoryItem(
            memory_id=item.memory_id,
            user_id=item.user_id,
            memory_type=item.memory_type,
            content=(content if content is not None else item.content).strip(),
            metadata=metadata if metadata is not None else item.metadata,
            confidence=_clamp_confidence(confidence) if confidence is not None else item.confidence,
            source=source if source is not None else item.source,
            status=status if status is not None else item.status,
            support_count=max(1, item.support_count + support_delta),
            created_at=item.created_at,
            updated_at=utc_now_iso(),
        )
        self._insert_or_replace(updated)
        return updated

    def list(
        self,
        user_id: str,
        memory_type: str | None = None,
        status: str | None = "active",
        limit: int = 80,
    ) -> list[MemoryItem]:
        query = """
            SELECT memory_id, user_id, memory_type, content, metadata_json,
                   confidence, source, status, support_count, created_at, updated_at
            FROM memories
            WHERE user_id = ?
        """
        params: list[Any] = [user_id]
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, memory_id: str) -> MemoryItem | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT memory_id, user_id, memory_type, content, metadata_json,
                       confidence, source, status, support_count, created_at, updated_at
                FROM memories
                WHERE memory_id = ?
                """,
                (memory_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def delete(self, memory_id: str) -> bool:
        with self._connect() as con:
            cursor = con.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
            return cursor.rowcount > 0

    def extract_and_update(
        self,
        user_id: str,
        question: str,
        answer: str,
        *,
        feedback: str = "",
        action: str = "auto_logged",
        accepted: bool = True,
    ) -> list[MemoryItem]:
        candidates = extract_memory_candidates(
            question=question,
            answer=answer,
            feedback=feedback,
            action=action,
            accepted=accepted,
        )
        updated = []
        for candidate in candidates:
            updated.append(self._merge_candidate(user_id, candidate))
        return updated

    def _merge_candidate(self, user_id: str, candidate: dict[str, Any]) -> MemoryItem:
        key = str(candidate["key"])
        memory_id = stable_id(f"{user_id}|{key}")
        metadata = dict(candidate.get("metadata", {}))
        metadata["key"] = key
        metadata["family"] = candidate.get("family", "")
        metadata["last_observed_at"] = utc_now_iso()
        metadata["signals"] = _trim_signals(metadata.get("signals", []))
        existing = self.get(memory_id)
        if not existing:
            return self.add(
                user_id=user_id,
                memory_type=str(candidate["memory_type"]),
                content=str(candidate["content"]),
                metadata=metadata,
                confidence=float(candidate["confidence"]),
                source="rule_extractor",
                memory_id=memory_id,
            )

        merged_metadata = {**existing.metadata, **metadata}
        merged_metadata["signals"] = _trim_signals(
            list(existing.metadata.get("signals", [])) + list(metadata.get("signals", []))
        )
        confidence = min(0.95, max(existing.confidence, float(candidate["confidence"])) + 0.03)
        return self.update(
            memory_id,
            content=str(candidate["content"]),
            metadata=merged_metadata,
            confidence=confidence,
            source="rule_extractor",
            status="active",
            support_delta=1,
        ) or existing

    def _insert_or_replace(self, item: MemoryItem) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO memories
                (memory_id, user_id, memory_type, content, metadata_json,
                 confidence, source, status, support_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.memory_id,
                    item.user_id,
                    item.memory_type,
                    item.content,
                    json.dumps(item.metadata, ensure_ascii=False),
                    item.confidence,
                    item.source,
                    item.status,
                    item.support_count,
                    item.created_at,
                    item.updated_at,
                ),
            )

    def _from_row(self, row: tuple[Any, ...]) -> MemoryItem:
        return MemoryItem(
            memory_id=row[0],
            user_id=row[1],
            memory_type=row[2],
            content=row[3],
            metadata=json.loads(row[4]),
            confidence=float(row[5]),
            source=row[6],
            status=row[7],
            support_count=int(row[8]),
            created_at=row[9],
            updated_at=row[10],
        )

    def _memory_id(
        self,
        user_id: str,
        memory_type: str,
        content: str,
        metadata: dict[str, Any],
    ) -> str:
        key = metadata.get("key")
        seed = f"{user_id}|{memory_type}|{key or content.strip().lower()}"
        return stable_id(seed)


def extract_memory_candidates(
    question: str,
    answer: str,
    feedback: str = "",
    action: str = "auto_logged",
    accepted: bool = True,
) -> list[dict[str, Any]]:
    del answer
    text = "\n".join([question, feedback, action]).lower()
    explicit_feedback = bool(feedback.strip()) or action != "auto_logged"
    signal = {
        "question": question.strip()[:240],
        "feedback": feedback.strip()[:240],
        "action": action,
        "accepted": accepted,
    }
    candidates: list[dict[str, Any]] = []

    if _contains_cjk(question):
        candidates.append(
            _candidate(
                key="language:zh",
                family="language",
                memory_type="response_preference",
                content="用户通常使用中文交流，默认优先用中文回答。",
                confidence=0.62,
                signal=signal,
            )
        )

    if _has_any(text, ["短一点", "简短", "少废话", "直接", "先给结论", "别太长", "不要长篇", "make_shorter"]):
        candidates.append(
            _candidate(
                key="length:concise_conclusion_first",
                family="length",
                memory_type="response_preference",
                content="用户偏好简洁回答，先给结论，避免长篇背景铺垫。",
                confidence=0.84 if explicit_feedback else 0.74,
                signal=signal,
            )
        )

    if _has_any(text, ["详细", "展开", "讲清楚", "完整", "make_more_detailed"]):
        candidates.append(
            _candidate(
                key="length:detailed_when_needed",
                family="length",
                memory_type="response_preference",
                content="用户在复杂问题上希望回答更详细、结构化，并补齐关键步骤。",
                confidence=0.8 if explicit_feedback else 0.68,
                signal=signal,
            )
        )

    if _has_any(text, ["表格", "对比", "add_table"]):
        candidates.append(
            _candidate(
                key="format:table_for_comparison",
                family="format",
                memory_type="output_format",
                content="复杂对比或方案权衡时，用户偏好使用表格。",
                confidence=0.86 if explicit_feedback else 0.72,
                signal=signal,
            )
        )

    if _has_any(text, ["代码", "实现", "落地", "模块", "工程", "add_code"]):
        candidates.append(
            _candidate(
                key="habit:engineering_first",
                family="task_habit",
                memory_type="task_habit",
                content="技术问题优先给工程落地建议，必要时补充代码路径或接口形态。",
                confidence=0.82 if explicit_feedback else 0.66,
                signal=signal,
            )
        )

    if _has_any(text, ["步骤", "一步步", "流程", "add_steps"]):
        candidates.append(
            _candidate(
                key="format:steps",
                family="format",
                memory_type="output_format",
                content="用户偏好把复杂任务拆成可执行步骤。",
                confidence=0.84 if explicit_feedback else 0.7,
                signal=signal,
            )
        )

    if _has_any(text, ["ppt", "展示", "答辩", "make_ppt"]):
        candidates.append(
            _candidate(
                key="format:presentation_ready",
                family="format",
                memory_type="output_format",
                content="面向展示或答辩时，用户偏好 PPT 友好的结构和表达。",
                confidence=0.82 if explicit_feedback else 0.7,
                signal=signal,
            )
        )

    if _has_any(text, ["不要太学术", "别太学术", "少点理论", "空泛", "太虚", "不实用"]):
        candidates.append(
            _candidate(
                key="avoid:academic_vague",
                family="avoid",
                memory_type="response_preference",
                content="用户希望避免过度学术化、空泛概念和不落地的背景铺垫。",
                confidence=0.84 if explicit_feedback else 0.74,
                signal=signal,
            )
        )

    if not accepted or _has_any(text, ["not_helpful", "没帮助", "不对", "错误", "不准确"]):
        candidates.append(
            _candidate(
                key="feedback:evidence_and_next_step",
                family="feedback",
                memory_type="response_preference",
                content="用户对无效或缺证据回答敏感；证据不足时要明确说明，并给出可执行下一步。",
                confidence=0.78 if explicit_feedback else 0.68,
                signal=signal,
            )
        )

    for key, label, keywords in TOPIC_RULES:
        if _has_any(text, keywords):
            candidates.append(
                _candidate(
                    key=key,
                    family="topic",
                    memory_type="topic_interest",
                    content=f"用户经常关注 {label} 相关问题。",
                    confidence=0.56,
                    signal=signal,
                )
            )

    return _dedupe_candidate_dicts(candidates)


def memory_prompt(memories: list[MemoryItem]) -> str:
    if not memories:
        return "无长期记忆命中。"
    lines = [
        "以下是用户长期记忆，只能用于调整表达方式、输出结构和任务习惯，不能当作事实证据："
    ]
    for item in memories:
        lines.append(
            f"- [{item.memory_type} confidence={item.confidence:.2f} support={item.support_count}] "
            f"{item.content}"
        )
    return "\n".join(lines)


def _candidate(
    key: str,
    family: str,
    memory_type: str,
    content: str,
    confidence: float,
    signal: dict[str, Any],
) -> dict[str, Any]:
    return {
        "key": key,
        "family": family,
        "memory_type": memory_type,
        "content": content,
        "confidence": confidence,
        "metadata": {"signals": [signal]},
    }


def _counter(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _metadata_search_text(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(0.99, value))


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _trim_signals(signals: Any) -> list[dict[str, Any]]:
    if not isinstance(signals, list):
        return []
    return [item for item in signals if isinstance(item, dict)][-6:]


def _dedupe_candidate_dicts(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for candidate in candidates:
        key = candidate["key"]
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result
