import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Brain,
  Database,
  FileUp,
  GitBranch,
  HeartPulse,
  NotebookText,
  RefreshCcw,
  Send,
  Sparkles
} from "lucide-react";
import {
  acceptCandidate,
  askQuestion,
  distillPreferences,
  generateContent,
  getProfile,
  healthCheck,
  listCandidates,
  listCards,
  listSystemLogs,
  rejectCandidate,
  reviewHealth,
  saveFeedback,
  uploadDocument
} from "./api";
import type { AskResponse, CardInfo, HealthReviewResponse, PreferenceCandidate, SystemLogInfo, UserProfile } from "./types";

type TabKey = "qa" | "wiki" | "health" | "memory" | "logs" | "generate";

const tabs: Array<{ key: TabKey; label: string; icon: typeof Database }> = [
  { key: "qa", label: "问答溯源", icon: Send },
  { key: "wiki", label: "Wiki", icon: Database },
  { key: "health", label: "健康审查", icon: HeartPulse },
  { key: "memory", label: "偏好记忆", icon: Brain },
  { key: "logs", label: "运行日志", icon: Activity },
  { key: "generate", label: "内容生成", icon: NotebookText }
];

export function App() {
  const [status, setStatus] = useState("正在连接后端");
  const [activeTab, setActiveTab] = useState<TabKey>("qa");
  const [cards, setCards] = useState<CardInfo[]>([]);
  const [logs, setLogs] = useState<SystemLogInfo[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("这个知识库目前有哪些核心能力？");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackAction, setFeedbackAction] = useState("accepted");
  const [health, setHealth] = useState<HealthReviewResponse | null>(null);
  const [candidates, setCandidates] = useState<PreferenceCandidate[]>([]);
  const [generated, setGenerated] = useState("");
  const [busy, setBusy] = useState(false);

  const spanEvidenceCount = useMemo(() => answer?.evidence.filter((item) => item.locator !== "wiki_card").length ?? 0, [answer]);

  async function refreshAll() {
    const [cardItems, logItems, profileInfo] = await Promise.all([listCards(), listSystemLogs(), getProfile()]);
    setCards(cardItems);
    setLogs(logItems);
    setProfile(profileInfo);
  }

  useEffect(() => {
    healthCheck()
      .then(() => refreshAll())
      .then(() => setStatus("后端已连接"))
      .catch(() => setStatus("未连接 FastAPI 后端"));
  }, []);

  async function handleUpload() {
    if (!file) return;
    setBusy(true);
    try {
      const result = await uploadDocument(file);
      setStatus(result.message);
      setFile(null);
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAsk() {
    setBusy(true);
    try {
      const result = await askQuestion(question);
      setAnswer(result);
      setStatus(`已生成回答，召回 ${result.evidence.length} 条证据`);
      await refreshAll();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "提问失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleFeedback() {
    if (!answer) return;
    await saveFeedback({
      question,
      answer_summary: answer.answer.slice(0, 600),
      answer_type: "technical_explanation",
      user_feedback: feedback,
      user_action: feedbackAction,
      accepted: feedbackAction !== "not_helpful"
    });
    setFeedback("");
    setStatus("反馈已保存，可进入偏好记忆蒸馏");
    await refreshAll();
  }

  async function handleHealth() {
    const result = await reviewHealth();
    setHealth(result);
    setStatus(`健康审查完成，发现 ${result.issues.length} 个问题`);
    await refreshAll();
  }

  async function handleDistill() {
    const result = await distillPreferences();
    setCandidates(result);
    setStatus(`生成 ${result.length} 条偏好候选`);
    await refreshAll();
  }

  async function refreshCandidates() {
    setCandidates(await listCandidates());
  }

  async function handleGenerate(kind: "note" | "report" | "ppt" | "mindmap") {
    const result = await generateContent(kind);
    setGenerated(result.content);
    setStatus(`已生成 ${kind}`);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>TraceWiki</h1>
          <p>{status}</p>
        </div>
        <div className="metrics" aria-label="知识库指标">
          <span><Database size={16} />{cards.length} Wiki</span>
          <span><GitBranch size={16} />{spanEvidenceCount} Span</span>
          <button className="icon-button" type="button" onClick={refreshAll} title="刷新">
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      <section className="upload-band">
        <label className="file-picker">
          <FileUp size={18} />
          <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <span>{file ? file.name : "选择资料文件"}</span>
        </label>
        <button className="primary-button" disabled={!file || busy} onClick={handleUpload} type="button">
          摄入并生成 Wiki
        </button>
      </section>

      <nav className="tabs" aria-label="功能区">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              className={activeTab === tab.key ? "active" : ""}
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              type="button"
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {activeTab === "qa" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>知识问答</h2>
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
            <button className="primary-button" disabled={busy} onClick={handleAsk} type="button">
              <Send size={16} />
              提问
            </button>
            <div className="feedback-row">
              <select value={feedbackAction} onChange={(event) => setFeedbackAction(event.target.value)}>
                <option value="accepted">整体可用</option>
                <option value="add_code">多给代码</option>
                <option value="add_table">多给表格</option>
                <option value="add_steps">多给步骤</option>
                <option value="make_shorter">更短</option>
                <option value="make_more_detailed">更详细</option>
                <option value="make_ppt">适合 PPT</option>
                <option value="not_helpful">没帮助</option>
              </select>
              <input value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="补充反馈" />
              <button type="button" onClick={handleFeedback} disabled={!answer}>保存反馈</button>
            </div>
          </div>
          <div className="panel">
            <h2>回答与证据</h2>
            {answer ? (
              <>
                <pre className="markdown-block">{answer.answer}</pre>
                <h3>证据工作图</h3>
                <pre className="code-block">{answer.graph_mermaid}</pre>
                <h3>证据片段</h3>
                <div className="evidence-list">
                  {answer.evidence.map((item, index) => (
                    <article key={`${item.source}-${index}`}>
                      <strong>{item.title}</strong>
                      <span>{item.locator} · score {item.score.toFixed(3)}</span>
                      <p>{item.snippet}</p>
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <p className="empty">输入问题后会显示回答、SourceSpan 证据和可复制的 Mermaid 图。</p>
            )}
          </div>
        </section>
      ) : null}

      {activeTab === "wiki" ? (
        <section className="workspace">
          <div className="panel">
            <h2>Wiki 卡片</h2>
            <div className="wiki-list">
              {cards.map((card) => (
                <article key={card.card_id}>
                  <strong>{card.title}</strong>
                  <span>{card.category} · {card.tags.join(", ")}</span>
                  <p>{card.summary}</p>
                  <details>
                    <summary>查看 Markdown</summary>
                    <pre>{card.content}</pre>
                  </details>
                </article>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === "health" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>知识库健康审查</h2>
            <button className="primary-button" onClick={handleHealth} type="button">
              <HeartPulse size={16} />
              开始审查
            </button>
            {health ? <pre className="markdown-block">{health.report_markdown}</pre> : <p className="empty">审查后会列出缺来源、覆盖不足、多模态缺失等问题。</p>}
          </div>
          <div className="panel">
            <h2>补全建议</h2>
            {health?.completion_actions.map((action) => (
              <article className="line-item" key={action.issue_title}>
                <strong>{action.action_type}</strong>
                <p>{action.query_or_request}</p>
                <span>{action.rationale}</span>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeTab === "memory" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>当前用户画像</h2>
            <pre className="code-block">{profile ? JSON.stringify(profile, null, 2) : "未加载"}</pre>
          </div>
          <div className="panel">
            <h2>偏好候选</h2>
            <div className="button-row">
              <button className="primary-button" onClick={handleDistill} type="button">
                <Sparkles size={16} />
                从历史蒸馏
              </button>
              <button type="button" onClick={refreshCandidates}>刷新候选</button>
            </div>
            {candidates.map((candidate) => (
              <article className="line-item" key={candidate.candidate_id}>
                <strong>{`${candidate.field}: ${candidate.old_value} -> ${candidate.new_value}`}</strong>
                <p>{candidate.evidence}</p>
                <span>confidence {candidate.confidence.toFixed(2)}</span>
                <div className="button-row">
                  <button onClick={() => acceptCandidate(candidate.candidate_id).then(refreshAll)} type="button">接受</button>
                  <button onClick={() => rejectCandidate(candidate.candidate_id).then(refreshCandidates)} type="button">拒绝</button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeTab === "logs" ? (
        <section className="workspace">
          <div className="panel">
            <h2>系统运行日志</h2>
            {logs.map((log) => (
              <article className="line-item" key={log.log_id}>
                <strong>{log.action_type}</strong>
                <span>{log.created_at}</span>
                <p>{log.summary}</p>
                <pre>{JSON.stringify(log.payload, null, 2)}</pre>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeTab === "generate" ? (
        <section className="workspace two-column">
          <div className="panel">
            <h2>内容生成</h2>
            <div className="button-grid">
              <button onClick={() => handleGenerate("note")} type="button">学习笔记</button>
              <button onClick={() => handleGenerate("report")} type="button">技术报告</button>
              <button onClick={() => handleGenerate("ppt")} type="button">PPT 大纲</button>
              <button onClick={() => handleGenerate("mindmap")} type="button">思维导图</button>
            </div>
          </div>
          <div className="panel">
            <h2>生成结果</h2>
            <pre className="markdown-block">{generated || "选择一种输出类型。"}</pre>
          </div>
        </section>
      ) : null}
    </main>
  );
}
