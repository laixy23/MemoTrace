from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from tracewiki.completion import propose_completion_actions, render_actions
from tracewiki.config import ensure_dirs, load_settings
from tracewiki.evidence_graph import build_evidence_graph, result_table
from tracewiki.generators import (
    generate_learning_note,
    generate_mindmap,
    generate_ppt_outline,
    generate_technical_report,
)
from tracewiki.health_check import render_health_report, review_knowledge_base
from tracewiki.ingest import ingest_path
from tracewiki.hybrid_retriever import HybridRetriever
from tracewiki.llm import ModelClient
from tracewiki.personalization import apply_candidate, load_profile, save_profile
from tracewiki.preference_distiller import create_interaction_log, distill_preferences
from tracewiki.qa import answer_question
from tracewiki.reranker import rerank_results
from tracewiki.storage import KnowledgeStore
from tracewiki.system_log import record_event


load_dotenv()
settings = load_settings()
ensure_dirs(settings)
store = KnowledgeStore(settings.sqlite_path, settings.wiki_dir)

st.set_page_config(page_title="TraceWiki", layout="wide")
st.title("TraceWiki")
st.caption("可追溯、多模态、会自检、会学习偏好的个人知识库智能助手")

profile_path = settings.data_dir / "user_profile.json"
profile = load_profile(profile_path)

with st.sidebar:
    st.header("手动偏好设置")
    st.caption("这是原来的显式设置方案，保留为备选。")
    profile.language = st.selectbox("语言", ["zh-CN", "en-US"], index=0)
    profile.answer_style = st.selectbox(
        "回答风格",
        ["结构化、偏详细", "简短直接", "面向答辩展示", "偏技术实现"],
        index=max(0, ["结构化、偏详细", "简短直接", "面向答辩展示", "偏技术实现"].index(profile.answer_style))
        if profile.answer_style in ["结构化、偏详细", "简短直接", "面向答辩展示", "偏技术实现"]
        else 0,
    )
    profile.technical_level = st.selectbox(
        "技术深度",
        ["入门", "本科/研究生初级", "工程实现", "研究综述"],
        index=max(0, ["入门", "本科/研究生初级", "工程实现", "研究综述"].index(profile.technical_level))
        if profile.technical_level in ["入门", "本科/研究生初级", "工程实现", "研究综述"]
        else 1,
    )
    profile.length_preference = st.selectbox(
        "长度偏好",
        ["简短", "中等偏详细", "详细"],
        index=max(0, ["简短", "中等偏详细", "详细"].index(profile.length_preference))
        if profile.length_preference in ["简短", "中等偏详细", "详细"]
        else 1,
    )
    profile.citation_required = st.checkbox("回答必须带来源", value=profile.citation_required)
    if st.button("保存手动偏好"):
        save_profile(profile_path, profile)
        st.success("偏好已保存")

tab_upload, tab_qa, tab_wiki, tab_health, tab_memory, tab_logs, tab_generate = st.tabs(
    ["资料摄入", "知识问答", "Wiki", "健康审查", "个性化记忆", "运行日志", "内容生成"]
)

with tab_upload:
    st.subheader("上传资料")
    uploads = st.file_uploader(
        "支持文本、PDF、Word、表格、代码、图片",
        accept_multiple_files=True,
        type=[
            "txt",
            "md",
            "pdf",
            "docx",
            "csv",
            "xlsx",
            "py",
            "js",
            "ts",
            "json",
            "png",
            "jpg",
            "jpeg",
            "webp",
        ],
    )
    if st.button("摄入并生成 Wiki 卡片", type="primary"):
        if not uploads:
            st.warning("请先上传文件")
        for upload in uploads:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(upload.name).suffix) as tmp:
                tmp.write(upload.getbuffer())
                tmp_path = Path(tmp.name)
            card = ingest_path(tmp_path, settings, store)
            st.success(f"已生成：{card.title}")
            st.code(card.content[:1200], language="markdown")

with tab_qa:
    st.subheader("基于知识库问答")
    question = st.text_input("输入问题", "这个知识库目前有哪些核心能力？")
    if st.button("提问", type="primary"):
        cards = store.list_cards()
        spans = store.list_spans()
        vectors = store.list_vectors()
        client = ModelClient(settings)
        record_event(
            store,
            "question_received",
            "Received user question",
            {"question": question, "card_count": len(cards), "span_count": len(spans), "vector_count": len(vectors)},
        )
        results = HybridRetriever(cards, spans, vectors, client).search(question, limit=15)
        results = rerank_results(question, results, client, limit=5)
        record_event(
            store,
            "retrieval_completed",
            f"Retrieved {len(results)} evidence items",
            {"result_titles": [item.title for item in results]},
        )
        answer = answer_question(question, results, profile, client)
        record_event(
            store,
            "answer_generated",
            "Generated source-grounded answer",
            {"claim_count": len(answer.claims), "answer_length": len(answer.text)},
        )
        st.session_state["last_question"] = question
        st.session_state["last_answer"] = answer.text
        st.session_state["last_evidence_graph"] = build_evidence_graph(question, answer)
        st.session_state["last_results"] = result_table(results)
        st.markdown(answer.text)
        with st.expander("证据链"):
            for claim in answer.claims:
                st.markdown(f"**Claim**: {claim.text}")
                st.json({"confidence": claim.confidence, "evidence": claim.evidence})
        with st.expander("证据工作图", expanded=True):
            st.code(st.session_state["last_evidence_graph"], language="mermaid")
            st.dataframe(st.session_state["last_results"], use_container_width=True)

    st.divider()
    st.subheader("记录本次反馈")
    st.caption("这些反馈会进入交互历史，之后用于蒸馏偏好候选。")
    last_question = st.session_state.get("last_question", question)
    last_answer = st.session_state.get("last_answer", "")
    feedback_action = st.selectbox(
        "你希望系统从这次交互学到什么？",
        [
            "accepted",
            "add_code",
            "add_table",
            "add_steps",
            "make_shorter",
            "make_more_detailed",
            "make_ppt",
            "not_helpful",
        ],
    )
    feedback_text = st.text_area("补充反馈", placeholder="例如：以后技术问题请多给模块划分和代码路径")
    accepted = st.checkbox("这次回答整体可接受", value=True)
    if st.button("保存交互反馈"):
        log = create_interaction_log(
            question=last_question,
            answer_summary=last_answer[:600],
            answer_type="technical_explanation",
            user_feedback=feedback_text,
            user_action=feedback_action,
            accepted=accepted,
        )
        store.add_interaction(log)
        st.success("反馈已保存，可在“个性化记忆”中蒸馏偏好。")

with tab_wiki:
    st.subheader("Wiki 知识卡片")
    cards = store.list_cards()
    st.write(f"当前卡片数：{len(cards)}")
    for card in cards:
        with st.expander(card.title):
            st.markdown(card.content)

with tab_health:
    st.subheader("知识库健康审查")
    if st.button("审查当前知识库", type="primary"):
        issues = review_knowledge_base(store.list_cards())
        record_event(
            store,
            "health_review_completed",
            f"Knowledge health review found {len(issues)} issues",
            {"issue_titles": [issue.title for issue in issues]},
        )
        st.markdown(render_health_report(issues))
        st.divider()
        st.markdown(render_actions(propose_completion_actions(issues)))

with tab_memory:
    st.subheader("个性化记忆")
    st.caption("新方案：从交互历史中蒸馏偏好候选，用户确认后才写入长期画像。")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### 当前用户画像")
        st.json(
            {
                "language": profile.language,
                "answer_style": profile.answer_style,
                "technical_level": profile.technical_level,
                "length_preference": profile.length_preference,
                "preferred_outputs": profile.preferred_outputs,
                "domain_focus": profile.domain_focus,
                "avoid": profile.avoid,
                "learned_preferences": profile.learned_preferences,
            }
        )
    with col_b:
        st.markdown("### 最近交互历史")
        logs = store.list_interactions(limit=20)
        st.write(f"已记录 {len(logs)} 条交互")
        for log in logs[:5]:
            with st.expander(f"{log.user_action} | {log.created_at}"):
                st.write(log.question)
                st.caption(log.user_feedback or "无补充反馈")

    if st.button("从历史蒸馏偏好候选", type="primary"):
        candidates = distill_preferences(store.list_interactions(limit=30), profile)
        if not candidates:
            st.info("历史信号还不够。多保存几次反馈后再蒸馏会更可靠。")
        for item in candidates:
            store.add_preference_candidate(item)
        if candidates:
            record_event(
                store,
                "preference_distilled",
                f"Created {len(candidates)} preference candidates",
                {"candidate_fields": [item.field for item in candidates]},
            )
            st.success(f"生成 {len(candidates)} 条候选偏好，请在下方确认。")

    st.markdown("### 待确认偏好候选")
    pending = store.list_preference_candidates(status="pending")
    if not pending:
        st.info("暂无待确认候选。")
    for item in pending:
        with st.expander(f"{item.field}: {item.old_value} -> {item.new_value}"):
            st.write(item.evidence)
            st.progress(min(1.0, item.confidence))
            col_accept, col_reject = st.columns(2)
            if col_accept.button("接受并写入画像", key=f"accept-{item.candidate_id}"):
                profile = apply_candidate(profile, item)
                save_profile(profile_path, profile)
                store.update_candidate_status(item.candidate_id, "accepted")
                record_event(
                    store,
                    "preference_candidate_accepted",
                    f"Accepted preference candidate {item.field}",
                    {"field": item.field, "new_value": item.new_value},
                )
                st.success("已写入用户画像，刷新后生效。")
            if col_reject.button("拒绝", key=f"reject-{item.candidate_id}"):
                store.update_candidate_status(item.candidate_id, "rejected")
                record_event(
                    store,
                    "preference_candidate_rejected",
                    f"Rejected preference candidate {item.field}",
                    {"field": item.field, "new_value": item.new_value},
                )
                st.warning("已拒绝该候选。")

with tab_logs:
    st.subheader("系统运行日志")
    st.caption("参考另一个仓库的 operation logs，用来展示系统刚才做了哪些步骤。")
    logs = store.list_system_logs(limit=80)
    if not logs:
        st.info("暂无系统运行日志。上传、提问、审查或蒸馏偏好后会出现记录。")
    for log in logs:
        with st.expander(f"{log.action_type} | {log.created_at}"):
            st.write(log.summary)
            st.json(log.payload)

with tab_generate:
    st.subheader("内容生成")
    cards = store.list_cards()
    output_type = st.selectbox("生成类型", ["学习笔记", "技术报告", "PPT 大纲", "Mermaid 思维导图"])
    if st.button("生成", type="primary"):
        if output_type == "学习笔记":
            st.markdown(generate_learning_note(cards))
        elif output_type == "技术报告":
            st.markdown(generate_technical_report(cards))
        elif output_type == "PPT 大纲":
            st.markdown(generate_ppt_outline(cards))
        else:
            st.code(generate_mindmap(cards), language="mermaid")
