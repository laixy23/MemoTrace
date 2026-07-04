from __future__ import annotations

from dataclasses import dataclass
import json

from .llm import json_or_empty
from .models import KnowledgeCard


@dataclass
class HealthIssue:
    title: str
    severity: str
    issue_type: str
    reason: str
    suggestion: str


def review_knowledge_base(cards: list[KnowledgeCard], client=None) -> list[HealthIssue]:
    issues: list[HealthIssue] = []
    if not cards:
        return [
            HealthIssue(
                title="知识库为空",
                severity="high",
                issue_type="coverage_gap",
                reason="当前没有可检索知识卡片。",
                suggestion="上传课程笔记、论文、代码或图片截图后再生成 Wiki 卡片。",
            )
        ]

    for card in cards:
        if not card.evidence:
            issues.append(
                HealthIssue(
                    title=f"{card.title} 缺少证据链",
                    severity="high",
                    issue_type="missing_source",
                    reason="该知识卡片没有绑定原始来源。",
                    suggestion="重新摄入原始文件，确保 Sources 区域和 evidence 字段存在。",
                )
            )
        if len(card.summary) < 30:
            issues.append(
                HealthIssue(
                    title=f"{card.title} 摘要过薄",
                    severity="medium",
                    issue_type="low_coverage",
                    reason="摘要不足以支持后续问答和内容生成。",
                    suggestion="上传更完整资料，或调用 LLM 重新生成摘要。",
                )
            )
        if card.category == "image":
            text = card.content.lower()
            if "ocr not available" in text:
                issues.append(
                    HealthIssue(
                        title=f"{card.title} 未完成 OCR",
                        severity="medium",
                        issue_type="multimodal_gap",
                        reason="图片只有占位 OCR 文本，缺少精确文字提取。",
                        suggestion="安装 OCR 引擎或使用带视觉能力的模型 API 重新处理。",
                    )
                )
            if "vlm not configured" in text:
                issues.append(
                    HealthIssue(
                        title=f"{card.title} 未完成 VLM 理解",
                        severity="medium",
                        issue_type="multimodal_gap",
                        reason="图片缺少版面、图表或上下文解释。",
                        suggestion="配置 VLM 后重新生成图片知识卡片。",
                    )
                )

    topics = collect_topic_counts(cards)
    for topic, count in topics.items():
        if count == 1 and topic not in {"knowledge", "image"}:
            issues.append(
                HealthIssue(
                    title=f"{topic} 覆盖不足",
                    severity="low",
                    issue_type="coverage_gap",
                    reason="该主题目前只出现在一个知识卡片中。",
                    suggestion="可联网查询公开资料，或提醒用户上传更权威的私有材料。",
                )
            )
    return issues + llm_review_issues(cards, client)


def collect_topic_counts(cards: list[KnowledgeCard]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in cards:
        for tag in card.tags:
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def llm_review_issues(cards: list[KnowledgeCard], client) -> list[HealthIssue]:
    if not getattr(client, "enabled", False) or not cards:
        return []
    payload = [
        {
            "title": card.title,
            "summary": card.summary,
            "tags": card.tags,
            "category": card.category,
            "source_path": card.source_path,
            "evidence_count": len(card.evidence),
            "content_excerpt": card.content[:1200],
        }
        for card in cards[:40]
    ]
    prompt = (
        "You audit a personal LLM Wiki for semantic gaps, missing evaluations, contradictions, weak sources, "
        "duplicate pages, and stale knowledge. Return JSON only: "
        "{\"issues\":[{\"title\":\"...\",\"severity\":\"low|medium|high\","
        "\"issue_type\":\"...\",\"reason\":\"...\",\"suggestion\":\"...\"}]}.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        data = json_or_empty(client.chat([{"role": "user", "content": prompt}]))
    except Exception:
        return []
    issues = []
    for item in data.get("issues", [])[:10] if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        reason = str(item.get("reason", "")).strip()
        suggestion = str(item.get("suggestion", "")).strip()
        if not title or not reason:
            continue
        issues.append(
            HealthIssue(
                title=title,
                severity=str(item.get("severity", "medium")).strip() or "medium",
                issue_type=str(item.get("issue_type", "semantic_gap")).strip() or "semantic_gap",
                reason=reason,
                suggestion=suggestion or "Review and enrich the related Wiki pages.",
            )
        )
    return issues


def render_health_report(issues: list[HealthIssue]) -> str:
    if not issues:
        return "# 知识库健康报告\n\n当前未发现明显问题。"
    lines = ["# 知识库健康报告", ""]
    for index, issue in enumerate(issues, start=1):
        lines.extend(
            [
                f"## {index}. {issue.title}",
                f"- 严重程度：{issue.severity}",
                f"- 类型：{issue.issue_type}",
                f"- 原因：{issue.reason}",
                f"- 建议：{issue.suggestion}",
                "",
            ]
        )
    return "\n".join(lines)
