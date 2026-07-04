# TraceWiki 技术方案

## 项目定位

TraceWiki 是一个可追溯、多模态、会自检、可个性化的个人知识库智能助手。系统面向学习、科研和开发场景，帮助用户把课程笔记、论文、博客、代码、表格和图片截图沉淀为长期可复用的知识资产。

项目参考 LLM-Wiki 思想：保留原始资料，将 AI 整理后的内容写成 Markdown Wiki，并让问答结果能够追溯到原始证据。

## 核心问题

普通 RAG 系统通常只完成：

```text
文件 -> 切片 -> 向量库 -> 问答
```

TraceWiki 进一步完成：

```text
文件 -> raw 原始资料
     -> OCR/VLM/Parser 多模态理解
     -> wiki 结构化知识卡片
     -> 检索索引
     -> 带证据链的问答和内容生成
     -> 知识审查与主动补全
```

## 核心能力

### 1. OCR + VLM 多模态摄入

图片资料采用双路处理：

- OCR：提取精确文字。
- VLM：理解图片版面、图表、场景、上下文含义。

二者合并为 Image Knowledge Card，使 PPT 拍照、白板、论文图、流程图、表格截图都能进入知识库。

### 2. Markdown Wiki 知识沉淀

系统将资料整理为人和 AI 都可读的 Markdown 页面。每个页面包含：

- 摘要
- 标签
- 分类
- 关键知识
- OCR 文本或视觉理解
- 原始来源

### 3. 可追溯问答

系统回答问题时，先检索 Wiki 卡片，再生成答案，并保留证据链：

```text
回答结论
 -> 检索片段
 -> Wiki 卡片
 -> 原始资料
 -> 页码 / 图片区域 / 表格行列 / 代码位置
```

### 4. 知识库健康审查

系统可以主动检查知识库缺陷：

- 知识库为空
- 卡片缺少来源
- 摘要过薄
- 图片缺少 OCR
- 图片缺少 VLM 理解
- 主题覆盖不足

### 5. 主动补全建议

系统根据缺陷类型决定补全方式：

- 公开技术知识：建议联网搜索，进入 staging 待确认。
- 用户私有知识：提醒用户上传材料。
- 低置信知识：不直接合并进正式知识库。

### 6. 个性化回答

系统维护用户偏好画像，包括：

- 语言
- 回答风格
- 技术深度
- 是否强制引用
- 偏好输出类型

个性化影响表达方式，不改变事实本身。

新的记忆链路拆成三层：

```text
用户提问
  -> RetrievalService 检索文档证据
  -> MemoryService 检索长期记忆
  -> GenerationService 生成回答
  -> 记录本轮问答
  -> LangMem Memory Library 抽取并整理偏好
  -> 写入长期记忆（正式模式用官方 Mem0，离线模式用 SQLite）
  -> 高置信稳定偏好自动或手动蒸馏成 data/wiki/skills 用户 Skill
```

其中长期记忆和 Skill 只影响回答结构、长度、格式和任务习惯；事实仍然必须来自已入库证据。

## 技术架构

```text
Streamlit UI
  |
  |-- ingest.py                 资料摄入
  |-- parsers.py                文本/PDF/Word/表格/代码解析
  |-- image_understanding.py    OCR + VLM 图片理解
  |-- wiki_builder.py           Markdown Wiki 生成
  |-- storage.py                SQLite + Markdown 文件存储
  |-- retriever.py              本地检索
  |-- retrieval_service.py      文档检索服务封装
  |-- memory.py                 SQLite 长期记忆服务
  |-- official_memory.py        LangMem Memory Library + Mem0 / SQLite 存储适配层
  |-- qa.py                     带证据问答
  |-- generation_service.py     注入证据、画像、记忆和 Skill 的生成服务
  |-- health_check.py           知识库审查
  |-- completion.py             补全建议
  |-- personalization.py        用户偏好
  |-- skill_distiller.py        稳定偏好 Skill 蒸馏
  |-- generators.py             笔记/报告/PPT/思维导图生成
```

## 技术栈

- 前端：Streamlit
- 本地数据库：SQLite
- 知识文件：Markdown
- 检索：MVP 使用词法检索，可扩展 Chroma/FAISS
- 文档解析：pypdf、python-docx、pandas
- 图片理解：OCR + OpenAI-compatible VLM API
- 问答生成：OpenAI-compatible LLM API，未配置时使用本地规则回退

## MVP 边界

当前代码实现了可运行 MVP：

- 支持上传和摄入多类文件。
- 支持生成 Wiki 卡片。
- 支持本地检索问答。
- 支持证据链展示。
- 支持知识健康审查。
- 支持补全建议。
- 支持用户偏好设置。
- 支持生成学习笔记、技术报告、PPT 大纲和 Mermaid 思维导图。

后续可增强：

- 接入 Chroma/FAISS 向量检索。
- 接入真实 Web 搜索和 staging 审核流。
- 图片区域 bbox 级证据定位。
- 代码仓库级解析。
- 更强的知识冲突检测。
