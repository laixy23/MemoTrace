from __future__ import annotations

from collections import Counter

from .models import InteractionLog, PreferenceCandidate
from .personalization import UserProfile
from .wiki_builder import stable_id


ACTION_TO_OUTPUT = {
    "add_code": "代码示例",
    "add_table": "表格",
    "make_ppt": "PPT大纲",
    "add_steps": "步骤",
}


def create_interaction_log(
    question: str,
    answer_summary: str,
    answer_type: str,
    user_feedback: str,
    user_action: str,
    accepted: bool,
) -> InteractionLog:
    seed = "|".join([question, answer_summary, answer_type, user_feedback, user_action, str(accepted)])
    return InteractionLog(
        log_id=stable_id(seed),
        question=question.strip(),
        answer_summary=answer_summary.strip()[:600],
        answer_type=answer_type,
        user_feedback=user_feedback.strip(),
        user_action=user_action,
        accepted=accepted,
    )


def distill_preferences(
    logs: list[InteractionLog],
    profile: UserProfile,
) -> list[PreferenceCandidate]:
    if not logs:
        return []

    candidates: list[PreferenceCandidate] = []
    feedback_text = "\n".join(log.user_feedback for log in logs).lower()
    actions = Counter(log.user_action for log in logs)
    answer_types = Counter(log.answer_type for log in logs)

    candidates.extend(_output_candidates(actions, profile, logs))
    candidates.extend(_style_candidates(feedback_text, profile, logs))
    candidates.extend(_level_candidates(actions, answer_types, profile, logs))
    candidates.extend(_avoid_candidates(feedback_text, profile, logs))
    return dedupe_candidates(candidates)


def _output_candidates(
    actions: Counter[str],
    profile: UserProfile,
    logs: list[InteractionLog],
) -> list[PreferenceCandidate]:
    candidates = []
    current = set(profile.preferred_outputs or [])
    for action, output in ACTION_TO_OUTPUT.items():
        count = actions[action]
        if count >= 2 and output not in current:
            candidates.append(
                candidate(
                    field="preferred_outputs",
                    old_value=", ".join(profile.preferred_outputs or []),
                    new_value=output,
                    evidence=f"最近 {len(logs)} 条交互中，用户 {count} 次选择或反馈需要“{output}”。",
                    confidence=min(0.95, 0.55 + count * 0.1),
                )
            )
    return candidates


def _style_candidates(
    feedback_text: str,
    profile: UserProfile,
    logs: list[InteractionLog],
) -> list[PreferenceCandidate]:
    rules = [
        (["少废话", "直接", "短一点", "简短"], "简短直接", "用户多次要求回答更直接或更短。"),
        (["详细", "展开", "讲清楚", "具体"], "结构化、偏详细", "用户多次要求更完整解释。"),
        (["答辩", "展示", "演示"], "面向答辩展示", "用户关注演示表达和答辩呈现。"),
        (["代码", "实现", "落地", "模块"], "偏技术实现", "用户反复要求实现路径、模块设计或代码思路。"),
    ]
    for keywords, new_value, evidence in rules:
        hits = sum(feedback_text.count(keyword) for keyword in keywords)
        if hits >= 2 and profile.answer_style != new_value:
            return [
                candidate(
                    field="answer_style",
                    old_value=profile.answer_style,
                    new_value=new_value,
                    evidence=f"{evidence} 触发词出现 {hits} 次，样本数 {len(logs)}。",
                    confidence=min(0.92, 0.58 + hits * 0.08),
                )
            ]
    return []


def _level_candidates(
    actions: Counter[str],
    answer_types: Counter[str],
    profile: UserProfile,
    logs: list[InteractionLog],
) -> list[PreferenceCandidate]:
    implementation_signal = actions["add_code"] + answer_types["technical_explanation"]
    if implementation_signal >= 3 and profile.technical_level != "工程实现":
        return [
            candidate(
                field="technical_level",
                old_value=profile.technical_level,
                new_value="工程实现",
                evidence=f"最近交互中出现 {implementation_signal} 次工程实现相关信号。",
                confidence=min(0.9, 0.55 + implementation_signal * 0.08),
            )
        ]
    return []


def _avoid_candidates(
    feedback_text: str,
    profile: UserProfile,
    logs: list[InteractionLog],
) -> list[PreferenceCandidate]:
    if feedback_text.count("空泛") + feedback_text.count("太虚") >= 2:
        if "空泛概念" not in set(profile.avoid or []):
            return [
                candidate(
                    field="avoid",
                    old_value=", ".join(profile.avoid or []),
                    new_value="空泛概念",
                    evidence=f"最近 {len(logs)} 条交互中，用户多次指出回答空泛。",
                    confidence=0.78,
                )
            ]
    return []


def candidate(
    field: str,
    old_value: str,
    new_value: str,
    evidence: str,
    confidence: float,
) -> PreferenceCandidate:
    seed = "|".join([field, old_value, new_value, evidence])
    return PreferenceCandidate(
        candidate_id=stable_id(seed),
        field=field,
        old_value=old_value,
        new_value=new_value,
        evidence=evidence,
        confidence=confidence,
    )


def dedupe_candidates(candidates: list[PreferenceCandidate]) -> list[PreferenceCandidate]:
    seen = set()
    result = []
    for item in candidates:
        key = (item.field, item.new_value)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
