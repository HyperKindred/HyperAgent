# HyperAgent 开发路线图

> 从个人 AI 助手到真正智能化的数字伴侣。
> 目标形态：融合 Siri 的实用性、JARVIS 的管家能力、Neuro 的陪伴感。

---

**目录**

1. [当前状态评估](#1-当前状态评估)
2. [急需修复的问题](#2-急需修复的问题)
3. [架构优化](#3-架构优化)
4. [分阶段路线图](#4-分阶段路线图)
5. [设计原则](#5-设计原则)

---

## 1. 当前状态评估

### 已实现的核心功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 谈话式日程管理 | ✅ | 自然语言 CRUD，中文时间解析（"后天下午3点半"），双通道（对话 + 日历 UI） |
| RAG 语义记忆 | ✅ | DeepSeek Embedding API 向量化 + 余弦相似度检索，API 不可用时自动降级 LIKE 搜索 |
| 对话持久化 | ✅ | LangGraph SqliteSaver 保存完整对话历史 + 工具调用链，重启不丢失 |
| 前端双视图 | ✅ | Vue 3 ChatView + CalendarView，跨渠道操作通知同步 |
| CLI 交互 | ✅ | /new /clear 等命令，无前端可用 |
| 测试覆盖 | ✅ | 39 个测试覆盖 repository CRUD + 工具函数，in-memory SQLite fixture |

### 架构优势

- **双 Session 模式** — repository 接受可选 Session 参数，测试注入内存 SQLite，工具调用自动创建
- **双 DB 分离** — 业务数据（hyperagent.db）vs 对话状态（checkpoints.db），职责隔离
- **跨渠道通知** — REST 操作写 CalendarNotification 表，agent 调用前消费并注入提示词
- **对话裁剪** — _trim_if_needed() 防 context window 溢出
- **领域分离** — agent / memory / schedule / api 四个域职责清晰

### 技术栈一览

| 层 | 技术 |
|----|------|
| LLM | DeepSeek V4 Flash（兼容 OpenAI 接口） |
| Agent 框架 | LangGraph create_react_agent |
| 后端 | FastAPI |
| 前端 | Vue 3 + TypeScript + Vite |
| 数据库 | SQLite（SQLAlchemy ORM + LangGraph SqliteSaver） |
| 向量 | DeepSeek Embedding API（外置，无本地向量库） |

---

## 2. 急需修复的问题

按严重程度排列。完成这一阶段后，项目从"能跑的 demo"变为"值得每天用"的工具。

### P1 — 必须修

#### 2.1 Session 泄漏风险

**位置:** app/memory/repository.py, app/schedule/repository.py

_s() 自动创建 Session，但错误路径不保证关闭。如果 db.commit() 或 db.refresh() 抛出异常，db.close() 不会执行。

**建议:** 改用 context manager 模式，集中管理 Session 生命周期，同时消除约 20 处手动 db.close() 判断，错误路径自动回滚 + 关闭。

#### 2.2 前端"新对话"按钮不创建真实线程

**位置:** frontend/src/views/ChatView.vue, frontend/src/store/chat.ts

clearChat() 只清空了 localStorage 和前端消息列表。后端 SqliteSaver 中的对话历史仍然完整，再次发送消息时 agent 仍然能看到所有历史。

**建议:** 前端调用 REST 接口生成新 thread_id，后端返回新 ID 后前端重置 store。

### P2 — 建议修

#### 2.3 Embedding API 无重试

**位置:** app/memory/embeddings.py

get_embedding() 直接 requests.post，没有任何重试逻辑。相比 LLM 调用有 max_retries=3，embedding 遇到瞬断会静默降级（embedding=None），存入的记忆无法被语义搜索检索到。

**建议:** 用 tenacity 或 urllib3.Retry 加 2-3 次重试，间隔递增。

#### 2.4 工具返回错误字符串被 LLM 当作成功

**位置:** app/agent/tools.py

所有 tool 在输入解析失败时返回字符串（如 "无法解析开始时间"），对 LangGraph 来说是"成功返回值"。LLM 不会知道真正出了错，也不会尝试修正参数重新调用。

**建议:** 不可恢复的错误用 raise ValueError()，让 ToolNode 捕获后返回 ToolMessage 错误，LLM 会看到调用失败并尝试修正。

#### 2.5 Agent 每次请求都重建

**位置:** app/agent/graph.py

build_agent() 每次创建新的 ChatOpenAI 实例 + create_react_agent + 全表扫描记忆。注释说约 100ms，但仍是不必要的开销。

**建议:** 缓存 agent 实例。如果 create_react_agent 的 prompt 用 Callable 形式有 bug（注释提过），至少缓存 LLM 实例和 checkpointer。

#### 2.6 ChatView 的 Markdown 渲染太简陋

**位置:** frontend/src/views/ChatView.vue

renderMarkdown() 只处理了加粗和换行。system prompt 中大量使用的 markdown（列表、代码块、引用）全都显示为纯文本。

**建议:** 引入 marked 或 markdown-it 做完整渲染。

---

## 3. 架构优化

中优先级的结构性改进。不修复也能跑，但越往后阻力越大。

#### 3.1 添加 Streaming 响应

**现状:** POST /api/chat 返回完整响应。对于"智能化 Siri/JARVIS"体验，用户期望看到 token 逐字出现。

**方案:** 后端用 Server-Sent Events 流式输出，前端用 ReadableStream 逐 token 渲染。这是用户体验从"工具感"到"对话感"最关键的一步。

#### 3.2 工具错误传播策略统一

当前 return string / raise exception 混用。建议统一：

- 用户输入解析失败 → return 友好的中文提示给用户
- 系统级异常（DB 连不上、API 超时） → raise 异常给 LangGraph 重试
- 业务逻辑错误（找不到 ID） → return 提示，也可以 raise ValueError

#### 3.3 Agent 缓存策略

在当前 "Callable prompt 有 bug" 的限制下：
- 缓存 ChatOpenAI 实例（它是有状态的连接池）
- 缓存 SqliteSaver checkpointer
- create_react_agent 本身轻量，可以每轮重建
- get_memory_context() 加简单缓存（TTL 30s），避免全表扫描

---

## 4. 分阶段路线图

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

- [ ] 定时提醒与通知系统（APScheduler + SQLite）
- [ ] 邮件集成（IMAP 读取 + SMTP 发送）
- [ ] 天气/新闻外部 API 工具
- [ ] Web 搜索工具（搜索 + 内容摘要）
- [ ] 多线程对话管理（前端显示历史线程列表）
- [ ] 基础的用户认证（单人模式 API key）

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
- [ ] Electron 桌面应用打包

### Phase 5 — 自主代理（长期愿景）

目标：agent 能自主规划、多步执行、跨时间协调。

- [ ] 长期目标追踪（记住目标，定期提醒进展）
- [ ] 多步任务执行
- [ ] 自主日程规划（根据习惯和待办自动安排时间块）
- [ ] 多 agent 协作（后台 agent 查资料，前台 agent 聊天）
- [ ] 工具/技能自主编排（根据任务描述动态组合能力）
- [ ] 隐私优先的本地推理支持（接入本地模型，敏感数据不离机）

---

## 5. 设计原则

以下原则指导后续所有开发决策：

1. **渐进增强** — 每个 Phase 的结果都是可用的独立版本，不依赖后续阶段的完成
2. **数据主权** — 用户数据默认存储在本地，云端能力仅为增强选项
3. **隐私优先** — 记忆、对话、日程等敏感数据不上传第三方服务
4. **模块化** — 每个新能力是一个独立领域包，遵循现有模式（models + repository + tool + test）
5. **测试保护** — 每个新 domain 都必须有对应的测试覆盖
6. **REST 优先** — 每个 agent 工具都配套 REST API，前端可直接调用
7. **体验驱动** — 技术决策优先考虑使用感受，而非技术炫技
