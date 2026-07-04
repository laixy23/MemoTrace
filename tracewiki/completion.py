from __future__ import annotations

from dataclasses import dataclass

from .health_check import HealthIssue


@dataclass
class CompletionAction:
    issue_title: str
    action_type: str
    query_or_request: str
    rationale: str


PUBLIC_TOPICS = {
    "RAG",
    "OCR",
    "VLM",
    "LLM",
    "Chroma",
    "FAISS",
    "SQLite",
    "Self-RAG",
    "CRAG",
    "RAGAS",
    "ColPali",
}


def propose_completion_actions(issues: list[HealthIssue]) -> list[CompletionAction]:
    actions = []
    for issue in issues:
        topic = issue.title.split()[0]
        if issue.issue_type in {"multimodal_gap", "missing_source"}:
            actions.append(
                CompletionAction(
                    issue_title=issue.title,
                    action_type="ask_user_upload",
                    query_or_request="请上传原始资料，或配置 OCR/VLM 后重新处理该来源。",
                    rationale="该问题依赖用户私有资料或本地源文件，不适合直接用网页资料替代。",
                )
            )
        elif any(public in issue.title for public in PUBLIC_TOPICS):
            actions.append(
                CompletionAction(
                    issue_title=issue.title,
                    action_type="web_search",
                    query_or_request=f"{topic} personal knowledge base RAG source attribution",
                    rationale="该问题属于公开技术知识，可联网检索权威资料后进入 staging 待确认。",
                )
            )
        else:
            actions.append(
                CompletionAction(
                    issue_title=issue.title,
                    action_type="ask_user_upload",
                    query_or_request="请上传课堂笔记、论文、代码仓库或项目文档补全该知识点。",
                    rationale="当前无法判断该知识是否属于公开知识，优先避免污染个人知识库。",
                )
            )
    return actions


def render_actions(actions: list[CompletionAction]) -> str:
    if not actions:
        return "当前没有需要补全的知识缺口。"
    lines = ["# 补全建议", ""]
    for action in actions:
        lines.extend(
            [
                f"## {action.issue_title}",
                f"- 动作：{action.action_type}",
                f"- 查询或请求：{action.query_or_request}",
                f"- 理由：{action.rationale}",
                "",
            ]
        )
    return "\n".join(lines)

