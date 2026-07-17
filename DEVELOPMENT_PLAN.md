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
| 🧠 **RAG 语义记忆** | 自动探测聊天供应商 Embedding，失败回退 OpenRouter；向量不可用时自动关键词检索 |
| 🔔 **定时提醒** | APScheduler + SQLite，到点弹窗原生通知，支持周期性提醒 |
| 🌐 **联网搜索** | DuckDuckGo → Bing 多后端兜底，selectolax 结构化解析，自动抓取内容摘要 |
| ☁️ **天气查询** | OpenWeatherMap / wttr.in 降级方案 |
| 🧮 **计算与换算** | 安全数学运算 + 单位换算（公里↔英里、温度、重量等） |
| 🕐 **时区时间** | 支持中文时区简称和 IANA 名称，自动时差计算 |
| 🖼️ **多模态图片** | Canvas 压缩 → base64 → 视觉模型理解，支持粘贴和上传 |
| 📎 **文件上传** | 解析 PDF / Word / TXT 内容给 agent 分析 |
| 🐙 **GitHub 集成** | 通知查询、Issue/PR 搜索与创建 |
| 📝 **Notion 集成** | 页面搜索、内容读取、页面创建、数据库查询 |
| 📧 **QQ 邮箱** | SMTP 发件 + IMAP 收件/搜索，支持中文编码 |
| 🖥️ **Electron 桌面** | 系统托盘 + 原生通知 + 后端自动管理，一键构建免安装版 |
| 💬 **自由对话** | 闲聊共情 + 个性化回复（基于语义记忆） |

### 当前技术栈

| 层 | 技术 |
|----|------|
| LLM 推理 | GPT-5.6 Terra（OpenAI 兼容供应商可配置） |
| 视觉理解 | 默认复用聊天模型，可独立配置 |
| Agent 框架 | LangGraph create_react_agent（**30 个工具**） |
| 向量记忆 | 自动探测 + OpenRouter qwen/qwen3-embedding-8b 回退（**214 个测试**） |
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
- **通知去重** — 原子 `mark_fired` + `threading.Lock` 保护 SSE 客户端，消除重复弹窗
- **时区统一** — `app/utils/time.py` 提供 `now()` / `ensure_utc()`，全部模型统一 UTC 存储
- **结构化搜索解析** — selectolax CSS 选择器替代手写正则，mock 测试覆盖
- **XSS 防护** — DOMPurify 清洗 marked 输出，防止 LLM 注入 HTML/脚本

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

### Phase 2.5 — 地基加固（3 周，v0.2.1）

目标：修复 Phase 1-2 中隐蔽的关键缺陷，确保记忆/提醒/搜索在真实使用中可靠。

> 已完成基础审计与 API 迁移，当前后端回归为 214 项测试。

- [x] **时区统一** — 创建 `app/utils/time.py`；日历 API 本地输入/UTC 存储/本地日期查询与展示统一（消除 off-by-N-hours）
- [x] **通知去重** — `fire_reminder` 原子 `mark_fired` + `threading.Lock` 保护 `_sse_clients`
- [x] **内存泄漏修复** — ReminderRepository 6 方法补 rollback，消除 `"cannot commit"` 异常
- [x] **记忆搜索性能** — 全表扫描 → `LIMIT 200` + `ORDER BY importance DESC LIMIT 5`
- [x] **Embedding 稳健** — 输入截断（24K chars）+ 余弦相似度维度校验
- [x] **Web 搜索重构** — selectolax 替代正则，21 个 mock 测试覆盖 DuckDuckGo/Bing
- [x] **APScheduler 测试** — 12 个测试覆盖通知去重、周期提醒重复触发、安全扫描与调度生命周期
- [x] **XSS 修复** — ChatView + DOMPurify 清洗 marked 输出
- [x] **前端错误处理** — CalendarView 所有 `catch {}` 改为错误提示；非乐观删除
- [x] **LocalStorage 防抖** — watch + debounce(500ms)，消除逐 token 卡顿
- [x] **杂项修复** — timezone_tool crash、异常吞咽、prompt 编号、数据库静默迁移

#### Phase 2.5 追加修复（v0.2.1）

- [x] **数据持久化** — `config.py` 支持 `HYPERAGENT_DATA_DIR` 环境变量，打包版数据存 `%APPDATA%/HyperAgent/`，版本更新不丢失
- [x] **Electron 单实例锁** — `app.requestSingleInstanceLock()` 防止重复启动导致数据混乱
- [x] **Vite 代理端口** — `vite.config.ts` 读取 `HYPERAGENT_PORT` 环境变量，解决 `electron:dev` 模式代理到 18080
- [x] **前端 dist 打包** — `extraResources` 改为包含整个 `backend-resources/`，前端文件随后端 exe 一起部署
- [x] **侧边栏线程丢失** — 去掉 `finally` 块中 `loadThreadList()` 覆盖侧边栏，防止 `createThread` API 失败时本地 ID 被空列表覆盖
- [x] **对话裁剪孤立 tool_call** — `_trim_if_needed` 清除残留的有 tool_call 无 ToolMessage 的 AI 消息
- [x] **菜单栏隐藏** — `autoHideMenuBar: true`
- [x] **后台节流** — `backgroundThrottling: false` 防止窗口最小化时定时器挂起
- [x] **`recall_facts_tool` 容错** — `search_similar` 加 try/except，防止内部异常传播到 LangGraph 导致 `len(None)` 崩溃

验证：后端 **214 项测试**，前端 `vue-tsc` + `vite build` 成功；便携版产物经 `.env` / 已知 Key 扫描验证。

### Phase 3 — 深度个性化（2-3 月）

目标：agent 真正"了解你"，能给出有个人上下文判断的建议。

**Phase 3.1 — 记忆系统重构（4-5 周）**

- [ ] **`MemoryStore` 接口抽象** — 定义 `Protocol`，当前 SQLite 实现适配，为后续换本地向量数据库做准备
- [ ] **引入 sqlite-vec** — 零外部依赖的 SQLite 向量扩展，替换全表扫描 + Python 余弦暴力计算
- [ ] **LLM 自动分类与重要性评估** — `remember_fact_tool` 串联分类器，自动判断 category/importance
- [x] **语义重复合并** — Agent 自动记录时仅对高度相似且向量兼容的记忆合并，保留较高重要性
- [ ] **LLM 自动摘要合并** — 对确认重复但表述不同的记忆生成可审计摘要，保留完整来源文本
- [x] **召回统计** — 记录 `last_recalled_at` 与 `recall_count`，在记忆管理页展示使用次数
- [x] **动态遗忘排序** — 基于召回统计和时间衰减调整提示词注入排序，不改写用户设置的重要性
- [ ] **实体关系图谱** — 用 LLM 从对话中抽取三元组（`(person, relation, entity)`），SQLite 递归 CTE 查

**Phase 3.2 — 主动能力升级（3-4 周）**

- [ ] **Background Agent 框架** — 基于 APScheduler CronTrigger + agent prompt，支持注册周期性任务（每日简报等）
- [ ] **用户画像推断** — 消费记忆分类数据，按周/月分析作息规律、兴趣偏好、沟通风格
- [ ] **主动建议引擎** — 条件触发式（"今晚有 event + 明日天气有雨 → 建议提前出门"），SSE 推送
- [ ] **情绪感知与自适应回应** — 用户输入时判断情绪倾向，系统提示词注入 `current_user_mood`

### Phase 3.5 — 配置系统与分发准备（2-3 周）

目标：让 HyperAgent 真正可分发——无需手动编辑 `.env`，首次启动即可用。

- [x] **配置 API** — `GET/PUT /api/settings` + 模型发现/能力测试，非敏感配置写用户数据目录
- [x] **首次启动配置** — 无有效模型凭据时自动进入设置页
- [x] **配置前端页面** — 供应商、API Key、聊天/视觉/Embedding 模型与索引状态
- [x] **对话风格偏好** — 简洁、均衡、详细三档回复风格，保存后下一轮对话即时生效
- [x] **密钥安全存储** — Windows 凭据管理器，发行包不再携带 `.env`
- [x] **一键分发构建** — `build-portable.bat` 输出无 `.env` 的可分发目录，并复制包内前端资源
- [x] **打包凭据隔离** — 打包后端不再向上查找开发 `.env`；旧成品被占用时构建明确失败，避免误交付旧版本
- [x] **配置缺失保护** — 首次启动自动进入设置；聊天接口在未配置时返回明确的设置引导

#### 配置与数据管理追加完成项

- [x] **供应商迁移** — “我的贾维斯”预设、聊天/视觉模型选择、模型列表发现与能力测试
- [x] **运行时偏好热更新** — 时区保存前校验；时间解析和周期提醒使用当前设置，无需重启
- [x] **安全回退** — Embedding 自动探测、OpenRouter 回退、关键词检索与向量重建；单条重建失败不中断批次
- [x] **用户数据管理** — 记忆 CRUD / JSON 导入导出；对话历史恢复、单线程 JSON 导出
- [x] **发布审计** — 打包产物不含 `.env` 或已知明文 Key；包内后端与前端入口烟测通过

### Phase 4 — 感知与行动边界（3-6 月）

目标：agent 能"看"和"做"，不局限于对话。

- [ ] 本地文件操作（读/写/搜索文件）
- [ ] 桌面/应用控制（类似 Computer Use）
- [ ] 浏览器控制（填表单、查信息、自动化操作）
- [ ] 语音输入（Whisper STT）
- [ ] 语音输出（GPT-SoVITS / Fish Speech TTS）
- [ ] 截图理解、桌面视觉感知与 Computer Use
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
3. **本地存储优先** — 记忆、对话和日程默认保存在本地；聊天、视觉与 Embedding 可调用用户配置的云端服务，后续支持本地推理和本地向量检索
4. **模块化** — 每个新能力是一个独立领域包，遵循现有模式（models + repository + tool + test）
5. **测试保护** — 每个新 domain 都必须有对应的测试覆盖
6. **REST 优先** — 每个 agent 工具都配套 REST API，前端可直接调用
7. **体验驱动** — 技术决策优先考虑使用感受，而非技术炫技

