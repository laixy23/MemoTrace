from __future__ import annotations

from pathlib import Path

from .config import Settings
from .llm import ModelClient
from .models import Answer, MemoryItem, SearchResult
from .personalization import load_profile
from .qa import answer_question
from .skill_distiller import load_user_skill


class GenerationService:
    def __init__(self, settings: Settings, profile_path: Path) -> None:
        self.settings = settings
        self.profile_path = profile_path

    def generate_answer(
        self,
        question: str,
        evidences: list[SearchResult],
        memories: list[MemoryItem],
        *,
        user_id: str = "default",
    ) -> Answer:
        profile = load_profile(self.profile_path)
        return answer_question(
            question=question,
            results=evidences,
            profile=profile,
            client=ModelClient(self.settings),
            memories=memories,
            skill=load_user_skill(self.settings.wiki_dir, user_id),
        )
