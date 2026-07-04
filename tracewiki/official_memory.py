from __future__ import annotations

import json
from typing import Any, Protocol

import requests

from .config import Settings
from .llm import ModelClient, json_or_empty
from .memory import MemoryService, extract_memory_candidates
from .models import MemoryItem, utc_now_iso
from .wiki_builder import stable_id


class MemoryServiceProtocol(Protocol):
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
        ...

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
    ) -> list[MemoryItem]:
        ...

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
        ...

    def list(
        self,
        user_id: str,
        memory_type: str | None = None,
        status: str | None = "active",
        limit: int = 80,
    ) -> list[MemoryItem]:
        ...

    def delete(self, memory_id: str) -> bool:
        ...

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
        ...


def create_memory_service(settings: Settings) -> MemoryServiceProtocol:
    backend = settings.memory_backend
    if backend == "auto":
        backend = "mem0" if settings.mem0_api_key else "sqlite"
    if backend == "mem0":
        return Mem0MemoryService(settings, create_preference_extractor(settings))
    if backend == "sqlite":
        return LocalMemoryServiceAdapter(
            MemoryService(settings.sqlite_path),
            create_preference_extractor(settings),
        )
    raise RuntimeError("TRACEWIKI_MEMORY_BACKEND must be auto, mem0, or sqlite.")


def create_preference_extractor(settings: Settings) -> "PreferenceExtractorProtocol":
    if settings.memory_extractor == "langmem":
        return LangMemPreferenceExtractor(settings.langmem_model)
    if settings.memory_extractor in {"rules", "rule"}:
        return RulePreferenceExtractor()
    if settings.memory_extractor in {"model", "llm", "openai"}:
        return ModelClientPreferenceExtractor(settings)
    raise RuntimeError("TRACEWIKI_MEMORY_EXTRACTOR must be model, rules, or langmem.")


class PreferenceExtractorProtocol(Protocol):
    def extract(
        self,
        question: str,
        answer: str,
        *,
        feedback: str = "",
        action: str = "auto_logged",
        accepted: bool = True,
    ) -> list[dict[str, Any]]:
        ...


class RulePreferenceExtractor:
    source_name = "rule_extractor"

    def extract(
        self,
        question: str,
        answer: str,
        *,
        feedback: str = "",
        action: str = "auto_logged",
        accepted: bool = True,
    ) -> list[dict[str, Any]]:
        return extract_memory_candidates(question, answer, feedback, action, accepted)


class ModelClientPreferenceExtractor:
    source_name = "model_extractor"

    def __init__(self, settings: Settings) -> None:
        self.client = ModelClient(settings)
        self.rule_fallback = RulePreferenceExtractor()
        self.last_source_name = self.source_name

    def extract(
        self,
        question: str,
        answer: str,
        *,
        feedback: str = "",
        action: str = "auto_logged",
        accepted: bool = True,
    ) -> list[dict[str, Any]]:
        if not self.client.enabled:
            self.last_source_name = self.rule_fallback.source_name
            return self.rule_fallback.extract(
                question,
                answer,
                feedback=feedback,
                action=action,
                accepted=accepted,
            )

        response = self.client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You extract durable user memory for TraceWiki. Return JSON only. "
                        "Extract response preferences, output format preferences, task habits, "
                        "recurring topics, and explicit feedback. Do not extract private factual "
                        "claims. Skip one-off requests unless framed as future preference."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Return this schema exactly:\n"
                        '{"memories":[{"memory_type":"response_preference|output_format|'
                        'task_habit|topic_interest|user_feedback","content":"中文偏好记忆",'
                        '"confidence":0.0,"evidence":"短证据","family":"format"}]}\n\n'
                        f"Question:\n{question}\n\n"
                        f"Answer:\n{answer[:1200]}\n\n"
                        f"Feedback:\n{feedback or 'none'}\n"
                        f"Action: {action}\nAccepted: {accepted}"
                    ),
                },
            ]
        )
        payload = json_or_empty(response)
        items = payload.get("memories", []) if isinstance(payload, dict) else []
        normalized = [_normalize_model_item(item) for item in items if isinstance(item, dict)]
        result = [item for item in normalized if item]
        if result:
            self.last_source_name = self.source_name
            return result

        self.last_source_name = self.rule_fallback.source_name
        return self.rule_fallback.extract(
            question,
            answer,
            feedback=feedback,
            action=action,
            accepted=accepted,
        )


class LangMemPreferenceExtractor:
    source_name = "langmem_extractor"

    def __init__(self, model: str) -> None:
        self.model = model
        self._manager: Any | None = None
        self.fallback = RulePreferenceExtractor()
        self.last_source_name = self.source_name

    def extract(
        self,
        question: str,
        answer: str,
        *,
        feedback: str = "",
        action: str = "auto_logged",
        accepted: bool = True,
    ) -> list[dict[str, Any]]:
        try:
            manager = self._get_manager()
            payload = {
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                    {
                        "role": "user",
                        "content": (
                            f"Explicit feedback: {feedback or 'none'}\n"
                            f"Feedback action: {action}\n"
                            f"Accepted: {accepted}"
                        ),
                    },
                ]
            }
            raw_memories = manager.invoke(payload)
        except Exception:
            self.last_source_name = self.fallback.source_name
            return self.fallback.extract(
                question,
                answer,
                feedback=feedback,
                action=action,
                accepted=accepted,
            )
        self.last_source_name = self.source_name
        return [item for item in (_normalize_langmem_item(raw) for raw in raw_memories) if item]

    def _get_manager(self) -> Any:
        if self._manager is not None:
            return self._manager
        try:
            from langmem import create_memory_manager
            from pydantic import BaseModel, Field
        except ImportError as exc:
            raise RuntimeError(
                "TRACEWIKI_MEMORY_EXTRACTOR=langmem requires installing the official "
                "`langmem` package."
            ) from exc

        class PreferenceMemory(BaseModel):
            memory_type: str = Field(
                description=(
                    "One of response_preference, output_format, task_habit, "
                    "topic_interest, user_feedback."
                )
            )
            content: str = Field(
                description="A concise, durable user preference or habit in Chinese."
            )
            confidence: float = Field(
                default=0.7,
                ge=0,
                le=1,
                description="Confidence that the memory should persist.",
            )
            evidence: str = Field(
                default="",
                description="Short evidence from the interaction, without copying raw private text verbatim.",
            )

        self._manager = create_memory_manager(
            self.model,
            schemas=[PreferenceMemory],
            instructions=(
                "Extract only durable user response preferences, output format preferences, "
                "task habits, recurring topics, or explicit feedback. Do not extract factual "
                "claims about the user's private knowledge base. Prefer Chinese content. "
                "Skip one-off requests unless the user clearly frames them as future preference."
            ),
        )
        return self._manager


class Mem0MemoryService:
    def __init__(
        self,
        settings: Settings,
        extractor: PreferenceExtractorProtocol | None = None,
    ) -> None:
        if not settings.mem0_api_key:
            raise RuntimeError("TRACEWIKI_MEMORY_BACKEND=mem0 requires MEM0_API_KEY.")
        self.settings = settings
        self.extractor = extractor or RulePreferenceExtractor()
        self.base_url = settings.mem0_base_url.rstrip("/")

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
        del memory_id
        metadata = {
            **(metadata or {}),
            "memory_type": memory_type,
            "confidence": confidence,
            "source": source,
            "status": status,
            "support_count": int((metadata or {}).get("support_count", 1)),
        }
        response = self._request(
            "POST",
            "/v3/memories/add/",
            json={
                "messages": [{"role": "user", "content": content}],
                "user_id": user_id,
                "metadata": metadata,
                "infer": False,
                "version": "v2",
            },
        )
        response_id = _first_string(response, ["event_id", "id", "memory_id"]) or stable_id(
            f"{user_id}|{memory_type}|{content}|{utc_now_iso()}"
        )
        return MemoryItem(
            memory_id=response_id,
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            confidence=confidence,
            source=source,
            metadata={**metadata, "mem0_response": response},
            status=status,
        )

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
    ) -> list[MemoryItem]:
        metadata: dict[str, Any] = {}
        if memory_type:
            metadata["memory_type"] = memory_type
        response = self._request(
            "POST",
            "/v3/memories/search/",
            json={
                "query": query,
                "user_id": user_id,
                "filters": metadata or None,
                "top_k": limit,
                "version": "v2",
            },
        )
        rows = _extract_rows(response)
        return [_mem0_row_to_item(row, default_user_id=user_id) for row in rows[:limit]]

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
        current = self.get(memory_id)
        if not current and content is None:
            return None
        merged_metadata = dict(current.metadata if current else {})
        if metadata:
            merged_metadata.update(metadata)
        if confidence is not None:
            merged_metadata["confidence"] = confidence
        if source is not None:
            merged_metadata["source"] = source
        if status is not None:
            merged_metadata["status"] = status
        if support_delta:
            merged_metadata["support_count"] = int(merged_metadata.get("support_count", 1)) + support_delta

        updated_content = content or (current.content if current else "")
        response = self._request(
            "PUT",
            f"/v1/memories/{memory_id}/",
            json={
                "memory": updated_content,
                "metadata": merged_metadata,
            },
        )
        if current:
            return MemoryItem(
                memory_id=memory_id,
                user_id=current.user_id,
                memory_type=str(merged_metadata.get("memory_type", current.memory_type)),
                content=updated_content,
                confidence=float(merged_metadata.get("confidence", current.confidence)),
                source=str(merged_metadata.get("source", current.source)),
                metadata={**merged_metadata, "mem0_response": response},
                status=str(merged_metadata.get("status", current.status)),
                support_count=int(merged_metadata.get("support_count", current.support_count)),
                created_at=current.created_at,
                updated_at=utc_now_iso(),
            )
        return None

    def list(
        self,
        user_id: str,
        memory_type: str | None = None,
        status: str | None = "active",
        limit: int = 80,
    ) -> list[MemoryItem]:
        params: dict[str, Any] = {"user_id": user_id, "page_size": limit}
        response = self._request("GET", "/v2/memories/", params=params)
        rows = _extract_rows(response)
        items = [_mem0_row_to_item(row, default_user_id=user_id) for row in rows]
        if memory_type:
            items = [item for item in items if item.memory_type == memory_type]
        if status:
            items = [item for item in items if item.status == status]
        return items[:limit]

    def get(self, memory_id: str) -> MemoryItem | None:
        try:
            response = self._request("GET", f"/v1/memories/{memory_id}/")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
        return _mem0_row_to_item(response, default_user_id="")

    def delete(self, memory_id: str) -> bool:
        try:
            self._request("DELETE", f"/v1/memories/{memory_id}/")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return False
            raise
        return True

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
        extracted = self.extractor.extract(
            question=question,
            answer=answer,
            feedback=feedback,
            action=action,
            accepted=accepted,
        )
        updated = []
        for item in extracted:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            metadata = dict(item.get("metadata", {}))
            metadata["evidence"] = item.get("evidence", "")
            metadata["key"] = item.get("key", stable_id(content))
            source = _extractor_source(self.extractor)
            memory_type = str(item.get("memory_type", item.get("type", "response_preference")))
            confidence = _safe_float(item.get("confidence"), 0.7)
            existing = self._find_existing_memory(
                user_id=user_id,
                key=str(metadata["key"]),
                content=content,
                memory_type=memory_type,
            )
            if existing:
                merged_metadata = _merge_memory_metadata(existing.metadata, metadata)
                merged_metadata["support_count"] = int(
                    merged_metadata.get("support_count", existing.support_count)
                ) + 1
                merged_confidence = min(0.95, max(existing.confidence, confidence) + 0.03)
                updated_item = self.update(
                    existing.memory_id,
                    content=content,
                    metadata=merged_metadata,
                    confidence=merged_confidence,
                    source=source,
                )
                if updated_item:
                    updated.append(updated_item)
                    continue

            updated.append(
                self.add(
                    user_id=user_id,
                    memory_type=memory_type,
                    content=content,
                    metadata=metadata,
                    confidence=confidence,
                    source=source,
                )
            )
        return updated

    def _find_existing_memory(
        self,
        user_id: str,
        key: str,
        content: str,
        memory_type: str,
    ) -> MemoryItem | None:
        candidates: list[MemoryItem] = []
        try:
            candidates.extend(self.list(user_id=user_id, memory_type=memory_type, limit=100))
        except requests.RequestException:
            pass
        try:
            candidates.extend(self.search(user_id=user_id, query=content, limit=10, memory_type=memory_type))
        except requests.RequestException:
            pass

        seen = set()
        for item in candidates:
            if item.memory_id in seen:
                continue
            seen.add(item.memory_id)
            if str(item.metadata.get("key", "")) == key:
                return item
        return None

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = requests.request(
            method,
            self.base_url + path,
            headers={
                "Authorization": f"Token {self.settings.mem0_api_key}",
                "Content-Type": "application/json",
            },
            json={key: value for key, value in (json or {}).items() if value is not None},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()


class LocalMemoryServiceAdapter:
    def __init__(
        self,
        backend: MemoryService,
        extractor: PreferenceExtractorProtocol,
    ) -> None:
        self.backend = backend
        self.extractor = extractor

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
        return self.backend.add(
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata,
            confidence=confidence,
            source=source,
            memory_id=memory_id,
            status=status,
        )

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
    ) -> list[MemoryItem]:
        return self.backend.search(user_id=user_id, query=query, limit=limit, memory_type=memory_type)

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
        return self.backend.update(
            memory_id,
            content=content,
            metadata=metadata,
            confidence=confidence,
            source=source,
            status=status,
            support_delta=support_delta,
        )

    def list(
        self,
        user_id: str,
        memory_type: str | None = None,
        status: str | None = "active",
        limit: int = 80,
    ) -> list[MemoryItem]:
        return self.backend.list(user_id=user_id, memory_type=memory_type, status=status, limit=limit)

    def delete(self, memory_id: str) -> bool:
        return self.backend.delete(memory_id)

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
        extracted = self.extractor.extract(
            question=question,
            answer=answer,
            feedback=feedback,
            action=action,
            accepted=accepted,
        )
        source = _extractor_source(self.extractor)
        updated = []
        for item in extracted:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            memory_type = str(item.get("memory_type", item.get("type", "response_preference")))
            key = str(item.get("key", stable_id(f"{memory_type}|{content}")))
            metadata = dict(item.get("metadata", {}))
            metadata["evidence"] = item.get("evidence", "")
            metadata["key"] = key
            memory_id = stable_id(f"{user_id}|{key}")
            updated.append(
                self.backend.add(
                    user_id=user_id,
                    memory_type=memory_type,
                    content=content,
                    metadata=metadata,
                    confidence=_safe_float(item.get("confidence"), 0.7),
                    source=source,
                    memory_id=memory_id,
                )
            )
        return updated


def _normalize_model_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    content = str(raw.get("content", "")).strip()
    if not content:
        return None
    memory_type = str(raw.get("memory_type", raw.get("type", "response_preference")))
    family = str(raw.get("family", memory_type))
    return {
        "key": stable_id(f"{memory_type}|{family}|{content}"),
        "memory_type": memory_type,
        "content": content,
        "confidence": _safe_float(raw.get("confidence"), 0.7),
        "evidence": str(raw.get("evidence", "")),
        "metadata": {"family": family},
    }


def _normalize_langmem_item(raw: Any) -> dict[str, Any] | None:
    item = raw
    if isinstance(raw, (list, tuple)) and raw:
        item = raw[-1]
    if hasattr(item, "model_dump"):
        data = item.model_dump()
    elif isinstance(item, dict):
        data = item
    elif hasattr(item, "dict"):
        data = item.dict()
    else:
        content = getattr(item, "content", "")
        data = {"content": content} if content else {}
    content = str(data.get("content", "")).strip()
    if not content:
        return None
    memory_type = str(data.get("memory_type", data.get("type", "response_preference")))
    return {
        "key": stable_id(f"{memory_type}|{content}"),
        "memory_type": memory_type,
        "content": content,
        "confidence": _safe_float(data.get("confidence"), 0.7),
        "evidence": str(data.get("evidence", "")),
        "metadata": {"family": data.get("family", memory_type)},
    }


def _mem0_row_to_item(row: dict[str, Any], default_user_id: str) -> MemoryItem:
    metadata = _coerce_dict(row.get("metadata"))
    memory_id = str(row.get("id") or row.get("memory_id") or stable_id(json.dumps(row, ensure_ascii=False)))
    content = str(row.get("memory") or row.get("content") or row.get("text") or "")
    confidence = _safe_float(metadata.get("confidence") or row.get("score"), 0.7)
    return MemoryItem(
        memory_id=memory_id,
        user_id=str(row.get("user_id") or metadata.get("user_id") or default_user_id),
        memory_type=str(metadata.get("memory_type", "response_preference")),
        content=content,
        confidence=confidence,
        source=str(metadata.get("source", "mem0")),
        metadata=metadata,
        status=str(metadata.get("status", "active")),
        support_count=int(metadata.get("support_count", 1)),
        created_at=str(row.get("created_at") or metadata.get("created_at") or utc_now_iso()),
        updated_at=str(row.get("updated_at") or metadata.get("updated_at") or utc_now_iso()),
    )


def _extract_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["results", "memories", "data"]:
        value = response.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_rows(value)
            if nested:
                return nested
    if response and any(key in response for key in ["memory", "content", "text"]):
        return [response]
    return []


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _merge_memory_metadata(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {**existing, **incoming}
    existing_signals = existing.get("signals", [])
    incoming_signals = incoming.get("signals", [])
    if isinstance(existing_signals, list) or isinstance(incoming_signals, list):
        merged["signals"] = [
            item
            for item in list(existing_signals if isinstance(existing_signals, list) else [])
            + list(incoming_signals if isinstance(incoming_signals, list) else [])
            if isinstance(item, dict)
        ][-6:]
    if existing.get("last_observed_at") or incoming.get("last_observed_at"):
        merged["last_observed_at"] = incoming.get("last_observed_at") or utc_now_iso()
    return merged


def _extractor_source(extractor: PreferenceExtractorProtocol) -> str:
    return str(getattr(extractor, "last_source_name", getattr(extractor, "source_name", "preference_extractor")))


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_string(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
