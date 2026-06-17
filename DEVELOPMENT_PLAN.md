# HyperAgent 开发路线图

> 从个人 AI 助手到真正智能化的数字伴侣。
> 目标形态：融合 Siri 的实用性、JARVIS 的管家能力、Neuro 的陪伴感。

---

**目录**

1. [当前完成状态](#1-当前完成状态)
2. [分阶段路线图](#2-分阶段路线图)
3. [设计原则](#3-设计原则)

---

## 1. 当前完成状态

### 已实现的核心功能

| 功能 | 说明 |
|------|------|
| 🤖 **流式对话** | SSE 逐 token 响应，前端 ReadableStream 消费，体验流畅 |
| 📅 **日程管理** | 自然语言 CRUD + 中文时间解析 + 日历 UI，双通道同步 |
| 🧠 **RAG 语义记忆** | OpenRouter Embedding API 向量化 + 余弦相似度检索，API 不可用自动降级 LIKE 搜索 |
| 🔔 **定时提醒** | APScheduler + SQLite，到点弹窗原生通知，支持周期性提醒 |
| 🌐 **联网搜索** | DuckDuckGo → Bing 多后端兜底，自动抓取内容摘要 |
| ☁️ **天气查询** | OpenWeatherMap / wttr.in 降级方案 |
| 🧮 **计算与换算** | 安全数学运算 + 单位换算（公里↔英里、温度、重量等） |
| 🕐 **时区时间** | 支持中文时区简称和 IANA 名称，自动时差计算 |
| 🖼️ **多模态图片** | Canvas 压缩 → base64 → 视觉模型理解，支持粘贴和上传 |
| 📎 **文件上传** | 解析 PDF / Word / TXT 内容给 agent 分析 |
| 🐙 **GitHub 集成** | 通知查询、Issue/PR 搜索与创建 |
| 📝 **Notion 集成** | 页面搜索、内容读取、页面创建、数据库查询 |
| 📧 **QQ 邮箱** | SMTP 发件 + IMAP 收件/搜索，支持中文编码 |
| 🖥️ **Electron 桌面** | 系统托盘 + 原生通知 + 后端自动管理 |
| 💬 **自由对话** | 闲聊共情 + 个性化回复（基于语义记忆） |

### 当前技术栈

| 层 | 技术 |
|----|------|
| LLM 推理 | DeepSeek V4 Flash（OpenCode Go 套餐） |
| 视觉理解 | Kimi K2.6（OpenCode） |
| Agent 框架 | LangGraph create_react_agent（**30 个工具**） |
| 向量记忆 | OpenRouter qwen/qwen3-embedding-8b（**124 个测试**） |
| 对话持久化 | LangGraph SqliteSaver |
| 后端 | FastAPI + uvicorn |
| 前端 | Vue 3 + TypeScript + Vite |
| 桌面 | Electron（系统托盘 + 原生通知） |
| 数据库 | SQLite（SQLAlchemy ORM） |
| 时间解析 | dateparser + 中文时间预处理 |

### 架构特性

- **双 DB 分离** — 业务数据（hyperagent.db）vs 对话状态（checkpoints.db）
- **双 Session 模式** — repository 接受可选 Session 参数，测试注入内存 SQLite
- **领域分离** — 每个能力独立域包（models + client/repository + tool + test）
- **跨渠道通知** — REST 操作 → CalendarNotification → agent 消费注入
- **对话裁剪** — _trim_if_needed() 防 context window 溢出
- **Agent 缓存** — ChatOpenAI 实例 + checkpointer 缓存

## 2. 分阶段路线图

### Phase 1 — 基础体验打磨（2 周）

目标：拥有一个"感觉对"的可用版本，值得每天使用。

- [x] Session context manager 重构（消除泄漏风险）
- [x] 前端"新对话"调用后端创建真实 thread
- [x] Embedding API 添加重试
- [x] 工具错误传播策略统一
- [x] Streaming 响应（SSE + 前端逐 token 渲染）
- [x] 前端 markdown 渲染升级
- [x] Agent 实例缓存优化

### Phase 2 — 主动能力（2-4 周）

目标：agent 从"你问我答"变成"会主动找你"。

- [x] 定时提醒与通知系统（APScheduler + SQLite）
- [x] 天气/新闻等更多工具
- [x] Web 搜索工具（搜索 + 内容摘要）
- [x] 多线程对话管理（前端显示历史线程列表）
- [x] 一键启动：Electron 桌面应用骨架（系统托盘 + 原生通知，`npm run electron:dev`）
- [x] 多模态支持
- [x] 文件上传处理（上传 PDF / Word / TXT / 图片给 agent 分析）
- [x] 第三方集成（GitHub / Notion / QQ 邮箱）

### Phase 3 — 深度个性化（2-3 月）

目标：agent 真正"了解你"，能给出有个人上下文判断的建议。

- [ ] 记忆系统升级：
  - LLM 自动判断类别和重要性
  - 记忆自动摘要与合并（避免重复信息膨胀）
  - 遗忘曲线（长时间未引用的记忆自动降低重要性）
  - 实体关系图谱
- [ ] 用户画像推断（作息规律、兴趣偏好、性格特征）
- [ ] 主动建议引擎（"你最近总熬夜"、"该准备下周的会了"）
- [ ] 情绪感知与适应该情绪状态的回应风格
- [ ] 引入本地向量数据库（Chroma / LanceDB），消除对外部 Embedding API 的依赖

### Phase 4 — 感知与行动边界（3-6 月）

目标：agent 能"看"和"做"，不局限于对话。

- [ ] 本地文件操作（读/写/搜索文件）
- [ ] 桌面/应用控制（类似 Computer Use）
- [ ] 浏览器控制（填表单、查信息、自动化操作）
- [ ] 语音输入（Whisper STT）
- [ ] 语音输出（GPT-SoVITS / Fish Speech TTS）
- [ ] 图像理解（看得懂截图、图片描述）
- [ ] 插件/技能系统（第三方可扩展能力）
- [x] Electron 桌面应用打包（骨架已提前到 Phase 2.1：系统托盘 + 原生通知 + 子进程管理）

### Phase 5 — 自主代理（长期愿景）

目标：agent 能自主规划、多步执行、跨时间协调。

- [ ] 长期目标追踪（记住目标，定期提醒进展）
- [ ] 多步任务执行
- [ ] 自主日程规划（根据习惯和待办自动安排时间块）
- [ ] 多 agent 协作（后台 agent 查资料，前台 agent 聊天）
- [ ] 工具/技能自主编排（根据任务描述动态组合能力）
- [ ] 隐私优先的本地推理支持（接入本地模型，敏感数据不离机）

## 3. 设计原则

以下原则指导后续所有开发决策：

1. **渐进增强** — 每个 Phase 的结果都是可用的独立版本，不依赖后续阶段的完成
2. **数据主权** — 用户数据默认存储在本地，云端能力仅为增强选项
3. **隐私优先** — 记忆、对话、日程等敏感数据不上传第三方服务
4. **模块化** — 每个新能力是一个独立领域包，遵循现有模式（models + repository + tool + test）
5. **测试保护** — 每个新 domain 都必须有对应的测试覆盖
6. **REST 优先** — 每个 agent 工具都配套 REST API，前端可直接调用
7. **体验驱动** — 技术决策优先考虑使用感受，而非技术炫技

