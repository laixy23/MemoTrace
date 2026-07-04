from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

import requests

from .config import Settings


class ModelClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openai_api_key)

    def chat(self, messages: list[dict[str, Any]], model: str | None = None) -> str:
        if not self.enabled:
            return ""
        url = self.settings.openai_base_url.rstrip("/") + "/chat/completions"
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or self.settings.text_model,
                "messages": messages,
                "temperature": 0.2,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]

    def vision(self, image_path: Path, prompt: str) -> str:
        if not self.enabled:
            return ""
        mime_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return self.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                        },
                    ],
                }
            ],
            model=self.settings.vision_model,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.enabled:
            return []
        url = self.settings.openai_base_url.rstrip("/") + "/embeddings"
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.settings.embedding_model, "input": texts},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]


def json_or_empty(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
        return {}
