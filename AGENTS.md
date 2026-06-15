# AGENTS.md

本文件为 Codex 提供此仓库的操作指引。

## 常用命令

```bash
# Python 后端 — 全部通过 uv
uv sync                                                    # 安装后端依赖
uv run pytest                                              # 运行全部测试（37 pass / 2 pre-existing skip）
uv run pytest tests/test_memory_repository.py -v           # 记忆仓库测试
uv run pytest tests/test_tools.py -v                       # 工具测试（含记忆工具）
uv run pytest tests/test_schedule_repository.py -v         # 日程仓库测试
uv run python main.py                                      # CLI 交互对话
uv run uvicorn app.main:app --port 8000 --reload           # 开发服务器（仅 API）

# 前端
cd frontend && npm install                                 # 安装前端依赖（仅首次）
cd frontend && npm run dev                                 # 开发服务器（5173 端口，/api 代理到 8000）
cd frontend && npm run build                               # 生产构建 → frontend/dist/
cd frontend && .\node_modules\.bin\vue-tsc --noEmit      # 仅类型检查（Windows）

# 改完后一键验证
uv run pytest && cd frontend && .\node_modules\.bin\vue-tsc --noEmit && npm run build
```

## 架构

### 双项目结构

仓库根目录既是 Python 项目根目录，也是 git 根目录。`frontend/` 是一个同级 npm 项目，不是 Python 子包。

### LLM 提供商

后端通过 OpenAI 兼容接口调用 LLM，默认使用 **OpenCode Go 套餐**（`https://opencode.ai/zen/go/v1`）。
模型配置在 `.env` 中：

| 环境变量 | 用途 | 默认值 |
|---------|------|--------|
| `LLM_BASE_URL` | 聊天 API 地址 | `https://opencode.ai/zen/go/v1` |
| `LLM_API_KEY` | OpenCode API Key | 需自行填写 |
| `LLM_MODEL` | 聊天模型 | `deepseek-v4-flash` |
| `EMBEDDING_BASE_URL` | 向量化 API 地址 | `https://api.deepseek.com/v1` |
| `EMBEDDING_API_KEY` | Embedding API Key | 默认复用 DEEPSEEK_API_KEY |
| `EMBEDDING_MODEL` | 向量化模型 | `deepseek-embedding` |

三个模型层各自独立配置，互不干扰：

- **LLM（聊天推理）** → OpenCode，$15/月 Go 套餐
- **Embedding（向量化）** → DeepSeek 按量计费（用量极小，基本免费）
- **搜索引擎** → DuckDuckGo → Bing 兜底 → 可选自定义 SEARCH_ENGINE_URL

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
├── ChatOpenAI（OpenCode / deepseek-v4-flash，streaming=True）
├── 11 个 @tool 工具函数
│   ├── 日程 CRUD（6 个：创建/列表/修改/删除/搜索/清除过期）
│   ├── 网络搜索（1 个：web_search_tool）
│   └── 记忆工具（3 个：记住/召回/删除）
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

记忆通过 DeepSeek Embedding API 向量化，语义搜索而非关键词匹配。

```
用户说"最近开始学吉他"
  → remember_fact_tool(content="用户最近开始学吉他...")
  → DeepSeek Embedding API → 向量存 SQLite

用户问"最近在忙什么"
  → recall_facts_tool(query="最近在忙什么")
  → DeepSeek Embedding API → 余弦相似度 → 匹配到"吉他"记忆
  → 如果 API 不可用，自动降级为 LIKE 文本搜索
```

记忆模型字段：`id, category, content(叙事文本), embedding(向量JSON), importance(0~1), source, timestamps`

### 两个 SQLite 数据库

| 文件 | 用途 | 管理者 |
|------|------|--------|
| `data/checkpoints.db` | 完整对话状态（消息、工具调用、结果） | LangGraph SqliteSaver |
| `data/hyperagent.db` | 业务数据：Event 表 + Memory 表 | SQLAlchemy |

两个数据库职责完全分离，互不干扰。

### LangChain 工具模式

工具定义在 `app/agent/tools.py`。每个工具是一个 `@tool` 装饰的函数。**docstring 必须中英双语**，并包含中文触发短语，确保 DeepSeek 能根据中文输入正确选择工具。所有工具注册在 `ALL_TOOLS` 列表中。

当前 11 个工具：
- `create_event_tool` / `list_events_tool` / `update_event_tool` / `delete_event_tool` / `search_events_tool` / `clear_expired_events_tool` / `get_current_datetime_tool`
- `web_search_tool`（DuckDuckGo → Bing 多后端搜索）
- `remember_fact_tool`（记住叙事内容，自动生成 embedding）
- `recall_facts_tool`（RAG 语义搜索，top-5 相关记忆）
- `forget_fact_tool`（按 ID 删除记忆）

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
5. 在 `tests/` 中添加测试

### 记忆注入系统提示词

`app/memory/context.py` 的 `get_memory_context()` 在每次 `run_agent()` 时被调用：
- 高重要性记忆（importance >= 0.8）+ 最新 5 条记忆 → 格式化文本块 → 注入系统提示词
- 深层语义检索由 LLM 主动调用 `recall_facts_tool` 完成

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
- **安全裁剪**：删除时会检查 AI 消息的 `tool_calls`，连带删除对应的 `tool` 响应消息，避免孤立的 tool role 消息导致 provider 报 400 错误。

### 配置

`app/config.py` 中的 `pydantic-settings` 从 `.env` 读取环境变量。单例 `settings` 实例被全后端引用。

主要配置分组：

| 分组 | 说明 |
|------|------|
| `llm_*` | 聊天 API（OpenCode / OpenAI 兼容接口） |
| `embedding_*` | 向量化 API（默认 DeepSeek） |
| `deepseek_*` | 向后兼容的嵌入配置兜底 |
| `search_engine_url` | 可选的自定义搜索引擎 URL |
| `max_history_messages` | 对话历史裁剪阈值（默认 40） |

### 消息持久化

前端的对话历史存储在 `localStorage`（key: `hyperagent-chat`，最多 100 条）。
通过 `frontend/src/store/chat.ts` 的 `watch` + `saveMessages()` 自动持久化。
使用 `deep: true` 监听，逐 token 流式追加时也会实时保存，页面刷新不丢最后的回答。

## 添加新功能

1. 在 `app/<domain>/` 下创建领域包（模型、仓库等）
2. 注册模型：在 `app/schedule/database.py` 的 `init_db()` 中 import
3. 在 `app/agent/tools.py` 中添加 `@tool` 函数，并追加到 `ALL_TOOLS`
4. 在 `app/agent/prompts.py` 中描述新能力
5. 可选：在 `app/api/<domain>.py` 中添加 REST 路由，在 `app/main.py` 中注册
6. 在 `tests/` 中添加测试
