from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import PreferenceCandidate


@dataclass
class UserProfile:
    language: str = "zh-CN"
    answer_style: str = "结构化、偏详细"
    technical_level: str = "本科/研究生初级"
    preferred_outputs: list[str] | None = None
    citation_required: bool = True
    length_preference: str = "中等偏详细"
    domain_focus: list[str] | None = None
    avoid: list[str] | None = None
    learned_preferences: list[dict[str, str | float | int]] | None = None

    def __post_init__(self) -> None:
        if self.preferred_outputs is None:
            self.preferred_outputs = ["步骤", "表格", "代码示例"]
        if self.domain_focus is None:
            self.domain_focus = ["RAG", "多模态", "项目落地"]
        if self.avoid is None:
            self.avoid = ["无来源结论", "过长背景铺垫"]
        if self.learned_preferences is None:
            self.learned_preferences = []


def load_profile(path: Path) -> UserProfile:
    if not path.exists():
        return UserProfile()
    data = json.loads(path.read_text(encoding="utf-8"))
    return UserProfile(**data)


def save_profile(path: Path, profile: UserProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(profile), ensure_ascii=False, indent=2), encoding="utf-8")


def profile_prompt(profile: UserProfile) -> str:
    outputs = ", ".join(profile.preferred_outputs or [])
    avoid = ", ".join(profile.avoid or [])
    focus = ", ".join(profile.domain_focus or [])
    learned = "; ".join(str(item.get("rule", "")) for item in profile.learned_preferences or [])
    return (
        f"用户语言: {profile.language}\n"
        f"回答风格: {profile.answer_style}\n"
        f"技术深度: {profile.technical_level}\n"
        f"长度偏好: {profile.length_preference}\n"
        f"领域关注: {focus}\n"
        f"偏好输出: {outputs}\n"
        f"必须引用来源: {profile.citation_required}\n"
        f"避免: {avoid}\n"
        f"历史蒸馏偏好: {learned}"
    )


def apply_candidate(profile: UserProfile, candidate: PreferenceCandidate) -> UserProfile:
    if candidate.field == "answer_style":
        profile.answer_style = candidate.new_value
    elif candidate.field == "technical_level":
        profile.technical_level = candidate.new_value
    elif candidate.field == "length_preference":
        profile.length_preference = candidate.new_value
    elif candidate.field == "preferred_outputs":
        current = list(profile.preferred_outputs or [])
        for value in split_values(candidate.new_value):
            if value and value not in current:
                current.append(value)
        profile.preferred_outputs = current
    elif candidate.field == "avoid":
        current = list(profile.avoid or [])
        for value in split_values(candidate.new_value):
            if value and value not in current:
                current.append(value)
        profile.avoid = current
    elif candidate.field == "domain_focus":
        current = list(profile.domain_focus or [])
        for value in split_values(candidate.new_value):
            if value and value not in current:
                current.append(value)
        profile.domain_focus = current

    learned = list(profile.learned_preferences or [])
    learned.append(
        {
            "rule": f"{candidate.field} -> {candidate.new_value}",
            "evidence": candidate.evidence,
            "confidence": round(candidate.confidence, 2),
        }
    )
    profile.learned_preferences = learned[-12:]
    return profile


def split_values(value: str) -> list[str]:
    separators = [",", "，", ";", "；", "|"]
    for sep in separators[1:]:
        value = value.replace(sep, separators[0])
    return [item.strip() for item in value.split(separators[0]) if item.strip()]
