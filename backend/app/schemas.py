from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    source_id: str
    path: str
    filename: str
    modality: str
    mime_type: str
    created_at: str


class CardInfo(BaseModel):
    card_id: str
    title: str
    summary: str
    tags: list[str]
    category: str
    source_id: str
    source_path: str
    content: str
    evidence: list[dict[str, Any]]
    created_at: str


class WikiPageInfo(BaseModel):
    filename: str
    content: str


class WikiProposalInfo(BaseModel):
    proposal_id: str
    proposal_type: str
    title: str
    rationale: str
    proposed_content: str
    target_card_id: str
    status: str
    created_at: str


class UploadResponse(BaseModel):
    card: CardInfo
    message: str


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    user_id: str = "default"


class EvidenceResult(BaseModel):
    title: str
    score: float
    locator: str
    source: str
    snippet: str


class MemoryInfo(BaseModel):
    memory_id: str
    user_id: str
    memory_type: str
    content: str
    metadata: dict[str, Any]
    confidence: float
    source: str
    status: str
    support_count: int
    created_at: str
    updated_at: str


class AskResponse(BaseModel):
    answer: str
    claims: list[dict[str, Any]]
    graph_mermaid: str
    evidence: list[EvidenceResult]
    memories: list[MemoryInfo] = Field(default_factory=list)
    memory_updates: list[MemoryInfo] = Field(default_factory=list)


class HealthIssueInfo(BaseModel):
    title: str
    severity: str
    issue_type: str
    reason: str
    suggestion: str


class CompletionActionInfo(BaseModel):
    issue_title: str
    action_type: str
    query_or_request: str
    rationale: str


class WebCompletionRequest(BaseModel):
    query: str
    limit: int = 3


class StagingItemInfo(BaseModel):
    staging_id: str
    title: str
    url: str
    summary: str
    content: str
    status: str
    created_at: str


class HealthReviewResponse(BaseModel):
    report_markdown: str
    issues: list[HealthIssueInfo]
    completion_actions: list[CompletionActionInfo]


class SystemLogInfo(BaseModel):
    log_id: str
    action_type: str
    summary: str
    payload: dict[str, Any]
    created_at: str


class InteractionFeedbackRequest(BaseModel):
    user_id: str = "default"
    question: str
    answer_summary: str
    answer_type: str = "technical_explanation"
    user_feedback: str = ""
    user_action: str = "accepted"
    accepted: bool = True


class PreferenceCandidateInfo(BaseModel):
    candidate_id: str
    field: str
    old_value: str
    new_value: str
    evidence: str
    confidence: float
    status: str
    created_at: str


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    metadata: dict[str, Any] | None = None
    confidence: float | None = None
    status: str | None = None


class MemoryCreateRequest(BaseModel):
    user_id: str = "default"
    memory_type: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.6
    source: str = "manual"


class SkillDistillResponse(BaseModel):
    updated: bool
    path: str
    content: str
    memory_count: int


class GenerateResponse(BaseModel):
    kind: str
    content: str
