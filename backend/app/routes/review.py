from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas import CompletionActionInfo, HealthIssueInfo, HealthReviewResponse
from backend.app.services import get_store
from tracewiki.completion import propose_completion_actions
from tracewiki.health_check import render_health_report, review_knowledge_base
from tracewiki.system_log import record_event

router = APIRouter(prefix="/health", tags=["review"])


@router.get("/review", response_model=HealthReviewResponse)
def review_knowledge() -> HealthReviewResponse:
    store = get_store()
    issues = review_knowledge_base(store.list_cards())
    actions = propose_completion_actions(issues)
    record_event(
        store,
        "health_review_completed",
        f"Knowledge health review found {len(issues)} issues",
        {"issue_titles": [issue.title for issue in issues]},
    )
    return HealthReviewResponse(
        report_markdown=render_health_report(issues),
        issues=[HealthIssueInfo(**issue.__dict__) for issue in issues],
        completion_actions=[CompletionActionInfo(**action.__dict__) for action in actions],
    )

