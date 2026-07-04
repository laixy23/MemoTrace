from __future__ import annotations

from .models import KnowledgeCard


def generate_learning_note(cards: list[KnowledgeCard]) -> str:
    lines = ["# 学习笔记", ""]
    for card in cards[:8]:
        lines.extend(
            [
                f"## {card.title}",
                card.summary,
                "",
                "关键标签：" + ", ".join(card.tags),
                f"来源：`{card.source_path}`",
                "",
            ]
        )
    return "\n".join(lines).strip()


def generate_technical_report(cards: list[KnowledgeCard]) -> str:
    lines = [
        "# 技术总结报告",
        "",
        "## 背景",
        "当前知识库围绕多模态个人知识库、可追溯问答、知识审查和个性化回答展开。",
        "",
        "## 主要知识点",
    ]
    for card in cards[:10]:
        lines.append(f"- **{card.title}**：{card.summary} 来源：`{card.source_path}`")
    lines.extend(
        [
            "",
            "## 风险与改进",
            "- 对缺少来源的知识点保持低置信度。",
            "- 对图片资料同时保留 OCR 文本和 VLM 理解。",
            "- 联网补全内容先进入 staging，用户确认后再合并。",
        ]
    )
    return "\n".join(lines)


def generate_ppt_outline(cards: list[KnowledgeCard]) -> str:
    feature_lines = "\n".join(f"- {card.title}" for card in cards[:6]) or "- 暂无知识卡片"
    return "\n".join(
        [
            "# PPT 大纲：可追溯多模态个人知识库助手",
            "",
            "## 1. 项目背景",
            "- 学习、科研、开发中存在大量碎片资料",
            "- 普通 RAG 缺少长期沉淀和证据链",
            "",
            "## 2. 方案概述",
            "- raw 原始资料库",
            "- wiki 结构化知识卡片",
            "- 检索问答与证据链",
            "- 知识审查与主动补全",
            "",
            "## 3. 核心功能",
            feature_lines,
            "",
            "## 4. 技术架构",
            "- Streamlit + SQLite + lexical/向量检索",
            "- OCR + VLM 多模态处理",
            "- LLM 生成摘要、标签、问答和报告",
            "",
            "## 5. 演示流程",
            "- 上传资料",
            "- 生成 Wiki",
            "- 提问并查看证据",
            "- 审查知识缺口",
            "- 生成报告/PPT/思维导图",
        ]
    )


def generate_mindmap(cards: list[KnowledgeCard]) -> str:
    lines = ["mindmap", "  root((TraceWiki))"]
    by_category: dict[str, list[KnowledgeCard]] = {}
    for card in cards:
        by_category.setdefault(card.category, []).append(card)
    for category, group in by_category.items():
        lines.append(f"    {category}")
        for card in group[:6]:
            title = card.title.replace("(", "").replace(")", "").replace(":", " ")
            lines.append(f"      {title[:40]}")
    return "\n".join(lines)
