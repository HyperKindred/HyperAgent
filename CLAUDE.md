# CLAUDE.md

本文件为 Claude Code 提供此仓库的操作指引。

## 常用命令

```bash
# Python 后端 — 全部通过 uv
uv sync                                                    # 安装后端依赖
uv run pytest                                              # 运行全部测试（124 个）
uv run pytest tests/test_memory_repository.py -v           # 记忆仓库测试
uv run pytest tests/test_tools.py -v                       # 工具测试（含记忆工具）
uv run pytest tests/test_schedule_repository.py -v         # 日程仓库测试
uv run python main.py                                      # CLI 交互对话
uv run uvicorn app.main:app --port 8000 --reload           # 开发服务器（仅 API）

# 前端
cd frontend && npm install                                 # 安装前端依赖（仅首次）
cd frontend && npm run dev                                 # 开发服务器（5173 端口，/api 代理到 8000）
cd frontend && npm run build                               # 生产构建 → frontend/dist/
cd frontend && npx vue-tsc --noEmit                        # 仅类型检查

# 改完后一键验证
uv run pytest && cd frontend && npx vue-tsc --noEmit && npm run build

# 功能完成后始终
git add -A && git commit -m "feat: 在此描述改动" && git push
```

## 架构

### 双项目结构

仓库根目录既是 Python 项目根目录，也是 git 根目录。`frontend/` 是一个同级 npm 项目，不是 Python 子包。

### LLM 提供商

后端通过 OpenAI 兼容接口调用 LLM。模型配置在 `.env` 中，四个模型层各自独立配置：

| 环境变量 | 用途 | 默认值 |
|---------|------|--------|
| `LLM_BASE_URL` | 聊天 API 地址 | `https://opencode.ai/zen/go/v1` |
| `LLM_API_KEY` | OpenCode API Key | 需填写 |
| `LLM_MODEL` | 聊天模型 | `deepseek-v4-flash` |
| `VISION_MODEL` | 多模态模型 | `kimi-k2.6` |
| `EMBEDDING_BASE_URL` | 向量化 API 地址 | `https://openrouter.ai/api/v1` |
| `EMBEDDING_API_KEY` | OpenRouter API Key | 需填写 |
| `EMBEDDING_MODEL` | 向量化模型 | `qwen/qwen3-embedding-8b` |

- **LLM（聊天推理）** → OpenCode，$15/月 Go 套餐
- **Vision（图片理解）** → OpenCode，共享套餐额度
- **Embedding（向量化）** → OpenRouter 按量计费，用量极小
- **搜索引擎** → DuckDuckGo → Bing 兜底

### 数据流（聊天）

```
用户输入 → ChatView.vue
          │
          ├─ POST /api/chat/stream（流式，默认）
          │      → stream_agent()
          │         → agent.astream_events(version="v2")
          │            → on_chat_model_stream 事件
          │               → 逐 token SSE data 事件
          │                  → fetch + ReadableStream
          │                     → chatStore 逐步追加
          │
          └─ POST /api/chat（非流式，后备）
                 → run_agent() → agent.invoke()

LangGraph agent 内部：
├── ChatOpenAI（streaming=True）
├── 11 个 @tool 工具函数
│   ├── 日程 CRUD（7 个）
│   ├── 网络搜索（1 个）
│   └── 记忆工具（3 个）
├── RAG 记忆注入（系统提示词）
└── SqliteSaver（checkpoints）
```

### 数据流（日历视图）

```
CalendarView.vue → GET /api/events → ScheduleRepository → SQLite（hyperagent.db）
```

### 网络搜索

`app/web_search/searcher.py` 实现了多后端兜底的搜索引擎：

```
搜索请求 → DuckDuckGo → 失败？ → Bing (cn.bing.com) → 失败？ → 自定义 SEARCH_ENGINE_URL
```

- **DuckDuckGo** 首选（POST `https://html.duckduckgo.com/html/`）
- **Bing 兜底**（GET `https://cn.bing.com/search`，国内可访问）
- **自定义 URL**（可选，通过 `.env` 的 `SEARCH_ENGINE_URL` 配置，兼容 SearXNG）
- 自动抓取首个结果正文内容

### RAG 个人记忆系统

记忆通过 OpenRouter Embedding API（qwen/qwen3-embedding-8b）向量化，语义搜索而非关键词匹配。

```
用户说"最近开始学吉他"
  → remember_fact_tool(content="用户最近开始学吉他...")
  → OpenRouter Embedding API → 4096 维向量存 SQLite

用户问"最近在忙什么"
  → recall_facts_tool(query="最近在忙什么")
  → OpenRouter Embedding API → 余弦相似度 → 匹配到"吉他"记忆
  → 如果 API 不可用，自动降级为 LIKE 文本搜索
```

记忆模型字段：`id, category, content(叙事文本), embedding(向量JSON), importance(0~1), source, timestamps`

### 多模态图片支持

用户可通过 **"+" 按钮** 或 **Ctrl+V 粘贴** 上传图片到对话。

```
用户上传图片
  → Canvas 压缩（最长边 1024px, JPEG quality 0.7）→ base64
  → POST /api/chat/stream { message, images: [base64...] }
  → graph.py 检测有图 → 自动切 vision_model（kimi-k2.6）
  → HumanMessage(content=[{type:text}, {type:image_url}])
  → LLM 视觉模型流式回复
  → 下一轮纯文本对话自动切回 LLM_MODEL
```

边界处理：
- 前端限制：单张 ≤ 5MB（原始），单次 ≤ 3 张，仅 png/jpeg/webp
- localStorage 不存 base64，只保留 `hasImages: true` 标记
- 刷新后显示 🖼️ 图片 占位标签
- Vision 模型在 `.env` 的 `VISION_MODEL` 中配置

### 两个 SQLite 数据库

| 文件 | 用途 | 管理者 |
|------|------|--------|
| `data/checkpoints.db` | 完整对话状态（消息、工具调用、结果） | LangGraph SqliteSaver |
| `data/hyperagent.db` | 业务数据：Event 表 + Memory 表 | SQLAlchemy |

两个数据库职责完全分离，互不干扰。

### LangChain 工具模式

工具定义在 `app/agent/tools.py`。每个工具是一个 `@tool` 装饰的函数。**docstring 必须中英双语**，并包含中文触发短语，确保 DeepSeek 能根据中文输入正确选择工具。所有工具注册在 `ALL_TOOLS` 列表中。

当前 30 个工具：
- **日程 CRUD（7 个）**— `create_event_tool` / `list_events_tool` / `update_event_tool` / `delete_event_tool` / `search_events_tool` / `clear_expired_events_tool` / `get_current_datetime_tool`
- **网络搜索（1 个）**— `web_search_tool`（DuckDuckGo → Bing 多后端搜索）
- **记忆工具（3 个）**— `remember_fact_tool` / `recall_facts_tool` / `forget_fact_tool`
- **天气/计算器/时区（3 个）**— `weather_query_tool` / `calculate_tool` / `timezone_tool`
- **定时提醒（3 个）**— `create_reminder_tool` / `list_reminders_tool` / `delete_reminder_tool`
- **GitHub（5 个）**— `github_list_notifications_tool` / `github_search_issues_tool` / `github_create_issue_tool` / `github_get_issue_tool` / `github_list_issues_tool`
- **Notion（4 个）**— `notion_search_tool` / `notion_read_page_tool` / `notion_create_page_tool` / `notion_query_database_tool`
- **QQ 邮箱（4 个）**— `send_email_tool` / `list_emails_tool` / `search_emails_tool` / `read_email_tool`

添加新工具：
```python
@tool
def new_tool(param: str) -> str:
    """中文描述。English description.
    触发短语："加xxx""查xxx"...
    """
    # 调用业务逻辑，返回字符串
```

### 新领域模式

添加新能力域的步骤：
1. 在 `app/<domain>/` 下创建包：`models.py`（ORM + Pydantic）+ `repository.py`（双 Session CRUD）
2. 在 `app/schedule/database.py` 的 `init_db()` 中 import 新模型
3. 在 `app/agent/tools.py` 中添加 `@tool` 函数，追加到 `ALL_TOOLS`
4. 在 `app/agent/prompts.py` 中添加能力描述
5. 可选：在 `app/api/<domain>.py` 中添加 REST 路由，在 `app/main.py` 中注册
6. 在 `tests/` 中添加测试

### 记忆注入系统提示词

`app/memory/context.py` 的 `get_memory_context()` 在每次 `run_agent()` 时被调用：
- 高重要性记忆（importance ≥ 0.8）+ 最新 5 条记忆 → 格式化文本块 → 注入系统提示词
- 深层语义检索由 LLM 主动调用 `recall_facts_tool` 完成

### 系统提示词能力

`app/agent/prompts.py` 中定义了 4 大能力领域，每个都有详细的行为指引：

1. **日程管理** — CRUD + 清除过期 + 查时间；强调必须通过工具获取实时数据
2. **个人记忆（RAG）** — 主动记录用户信息，语义检索，按类别（personal_info/preference/goal/note）组织
3. **联网搜索** — 体育赛事、新闻、天气、娱乐等话题必须主动搜索；拒绝瞎编
4. **自由对话** — 闲聊共情，不需要每轮都使用工具

跨渠道通知：`drain_notifications()` 消费日历页面直接操作的变更，注入到系统提示词中让 agent 感知。

### 中文日期解析

`_preprocess_chinese_time()` 先将"点/半/分"中文表达转换为 `HH:MM` 格式，再交给 `dateparser` 解析。此函数位于 `app/agent/tools.py`，所有涉及时间的工具共用。

### 前端路由

Vue Router 有两个视图：`/`（ChatView 对话页）和 `/calendar`（CalendarView 日程页）。

- **开发模式**：Vite 开发服务器（5173）通过 `vite.config.ts` 中的 proxy 配置将 `/api` 请求转发到 FastAPI（8000）。
- **生产模式**：FastAPI 挂载 `frontend/dist/assets/` 到 `/assets`，并用一条 catch-all 路由返回 `index.html` 实现 SPA 回退。两个模式 API 代码不变。

### 双 Session 模式

`ScheduleRepository` 和 `MemoryRepository` 都接受可选的 `Session` 参数。传入时（如 FastAPI 依赖注入或测试夹具）使用该会话；不传时自动从 `SessionLocal` 新建。测试通过 `conftest.py` 传入内存 SQLite 会话。

### 对话记忆管理

`app/agent/graph.py` 的 `_trim_if_needed()` 在每次 `run_agent()` 调用前自动裁剪历史。
- 通过 `settings.max_history_messages` 控制（默认 40），设为 0 则不裁剪。
- 实现方式：用 LangGraph 的 `RemoveMessage` 删除最旧消息，兼容 `add_messages` reducer。
- 系统提示词不在 `messages` 列表中（由 `create_react_agent` 每次自动注入），不受裁剪影响。
- 每轮对话增加 2 条（user + AI），峰值到 `max + 2` 条后下次裁回 `max`。
- **安全裁剪**：删除时会检查 AI 消息的 `tool_calls`，连带删除对应的 `tool` 角色响应消息，避免孤立的 tool role 消息导致 provider 报 400 错误。

### 前端消息持久化

前端的对话历史存储在 `localStorage`（key: `hyperagent-chat`，最多 100 条）。
通过 `frontend/src/store/chat.ts` 的 `watch` + `saveMessages()` 自动持久化。
使用 `deep: true` 监听，逐 token 流式追加时也会实时保存，页面刷新不丢最后的回答。

### 配置

`app/config.py` 中的 `pydantic-settings` 从 `.env` 读取环境变量。单例 `settings` 实例被全后端引用。新的配置项直接追加在 `.env` 末尾即可。

主要配置分组：

| 分组 | 说明 |
|------|------|
| `llm_*` | 聊天 API（OpenCode / OpenAI 兼容接口） |
| `vision_model` | 多模态模型名 |
| `embedding_*` | 向量化 API（OpenRouter / OpenAI 兼容接口） |
| `github_*` | GitHub Personal Access Token |
| `notion_*` | Notion Integration Token |
| `qq_email_*` | QQ 邮箱地址与授权码 |
| `weather_*` | OpenWeatherMap API Key |
| `search_engine_url` | 可选的自定义搜索引擎 URL |
| `timezone` | 时区（默认 Asia/Shanghai） |
| `log_level` | 日志级别 |
| `max_history_messages` | 对话历史裁剪阈值（默认 40） |

### REST API 路由

| 路由 | 功能 |
|------|------|
| `POST /api/chat/stream` | 流式聊天（SSE，默认） |
| `POST /api/chat` | 非流式聊天（后备） |
| `GET /api/events` | 获取日程列表 |
| `POST /api/events` | 创建日程 |
| `PUT /api/events/{id}` | 更新日程 |
| `DELETE /api/events/{id}` | 删除日程 |
| `GET /api/reminders` | 获取提醒列表 |
| `POST /api/reminders` | 创建提醒 |
| `DELETE /api/reminders/{id}` | 删除提醒 |
| `GET /api/threads` | 获取对话线程列表 |
| `POST /api/threads` | 创建新线程 |
| `GET /api/health` | 健康检查 |

所有 REST 操作写 `CalendarNotification` 表，agent 调用前通过 `drain_notifications()` 消费并注入提示词，实现跨渠道操作同步。

## 设计原则

以下原则指导后续所有开发决策：

1. **渐进增强** — 每个阶段的结果都是可用的独立版本，不依赖后续阶段的完成
2. **数据主权** — 用户数据默认存储在本地，云端能力仅为增强选项
3. **隐私优先** — 记忆、对话、日程等敏感数据不上传第三方服务
4. **模块化** — 每个新能力是一个独立领域包，遵循现有模式（models + repository + tool + test）
5. **测试保护** — 每个新 domain 都必须有对应的测试覆盖
6. **REST 优先** — 每个 agent 工具都配套 REST API，前端可直接调用
7. **体验驱动** — 技术决策优先考虑使用感受，而非技术炫技

## 已知问题

来自 DEVELOPMENT_PLAN.md 中标记为待修复的问题已全部在 Phase 1-2 中解决：

- [x] Session context manager 重构（消除泄漏风险）
- [x] 前端"新对话"调用后端创建真实 thread
- [x] Embedding API 添加重试
- [x] 工具错误传播策略统一（return string vs raise 混用已收敛）
- [x] Streaming 响应（SSE + 前端逐 token 渲染）
- [x] 前端 markdown 渲染升级
- [x] Agent 实例缓存优化
- [x] 三个第三方集成（GitHub / Notion / QQ 邮箱）

## 添加新功能

1. 在 `app/<domain>/` 下创建领域包（模型、仓库等）
2. 注册模型：在 `app/schedule/database.py` 的 `init_db()` 中 import
3. 在 `app/agent/tools.py` 中添加 `@tool` 函数，并追加到 `ALL_TOOLS`
4. 在 `app/agent/prompts.py` 中描述新能力
5. 可选：在 `app/api/<domain>.py` 中添加 REST 路由，在 `app/main.py` 中注册
6. 在 `tests/` 中添加测试
