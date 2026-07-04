from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from backend.app.schemas import InteractionFeedbackRequest, PreferenceCandidateInfo
from backend.app.services import get_settings, get_store
from tracewiki.personalization import apply_candidate, load_profile, save_profile
from tracewiki.preference_distiller import create_interaction_log, distill_preferences
from tracewiki.system_log import record_event

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("/profile")
def get_profile() -> dict:
    settings = get_settings()
    return asdict(load_profile(settings.data_dir / "user_profile.json"))


@router.post("/feedback")
def save_feedback(payload: InteractionFeedbackRequest) -> dict[str, str]:
    store = get_store()
    log = create_interaction_log(
        question=payload.question,
        answer_summary=payload.answer_summary,
        answer_type=payload.answer_type,
        user_feedback=payload.user_feedback,
        user_action=payload.user_action,
        accepted=payload.accepted,
    )
    store.add_interaction(log)
    record_event(
        store,
        "interaction_feedback_saved",
        "Saved user feedback for preference distillation",
        {"user_action": payload.user_action, "accepted": payload.accepted},
    )
    return {"status": "ok", "log_id": log.log_id}


@router.get("/interactions")
def list_interactions() -> list[dict]:
    return [asdict(log) for log in get_store().list_interactions(limit=30)]


@router.post("/distill", response_model=list[PreferenceCandidateInfo])
def distill() -> list[PreferenceCandidateInfo]:
    store = get_store()
    settings = get_settings()
    profile = load_profile(settings.data_dir / "user_profile.json")
    candidates = distill_preferences(store.list_interactions(limit=30), profile)
    for candidate in candidates:
        store.add_preference_candidate(candidate)
    if candidates:
        record_event(
            store,
            "preference_distilled",
            f"Created {len(candidates)} preference candidates",
            {"candidate_fields": [item.field for item in candidates]},
        )
    return [PreferenceCandidateInfo(**candidate.__dict__) for candidate in candidates]


@router.get("/candidates", response_model=list[PreferenceCandidateInfo])
def list_candidates() -> list[PreferenceCandidateInfo]:
    return [
        PreferenceCandidateInfo(**candidate.__dict__)
        for candidate in get_store().list_preference_candidates(status="pending")
    ]


@router.post("/candidates/{candidate_id}/accept")
def accept_candidate(candidate_id: str) -> dict[str, str]:
    store = get_store()
    settings = get_settings()
    candidates = [item for item in store.list_preference_candidates() if item.candidate_id == candidate_id]
    if not candidates:
        raise HTTPException(status_code=404, detail="Candidate not found")
    profile_path = settings.data_dir / "user_profile.json"
    profile = apply_candidate(load_profile(profile_path), candidates[0])
    save_profile(profile_path, profile)
    store.update_candidate_status(candidate_id, "accepted")
    record_event(
        store,
        "preference_candidate_accepted",
        f"Accepted preference candidate {candidates[0].field}",
        {"field": candidates[0].field, "new_value": candidates[0].new_value},
    )
    return {"status": "accepted"}


@router.post("/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str) -> dict[str, str]:
    get_store().update_candidate_status(candidate_id, "rejected")
    return {"status": "rejected"}

