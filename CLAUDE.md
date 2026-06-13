# CLAUDE.md

本文件为 Claude Code 提供此仓库的操作指引。

## 常用命令

```bash
# Python 后端 — 全部通过 uv
uv sync                                                    # 安装后端依赖
uv run pytest                                              # 运行全部测试（22 个）
uv run pytest tests/test_schedule_repository.py -v         # 单独跑某个测试文件
uv run python main.py                                      # CLI 交互对话
uv run uvicorn app.main:app --port 8000 --reload           # 开发服务器（仅 API）

# 前端
cd frontend && npm install                                 # 安装前端依赖（仅首次）
cd frontend && npm run dev                                 # 开发服务器（5173 端口，/api 代理到 8000）
cd frontend && npm run build                               # 生产构建 → frontend/dist/
cd frontend && npx vue-tsc --noEmit                        # 仅类型检查

# 改完后一键验证
uv run pytest && cd frontend && npx vue-tsc --noEmit && npm run build
```

## 架构

### 双项目结构

仓库根目录既是 Python 项目根目录，也是 git 根目录。`frontend/` 是一个同级 npm 项目，不是 Python 子包。

### 数据流（聊天）

```
用户输入（Vue / CLI）→ POST /api/chat → run_agent() → LangGraph agent
                                                        ├── ChatOpenAI（DeepSeek V4 Flash）
                                                        ├── 6 个 @tool 工具函数
                                                        └── SqliteSaver（checkpoints）
```

### 数据流（日历视图）

```
CalendarView.vue → GET /api/events → ScheduleRepository → SQLite（hyperagent.db）
```

### 两个 SQLite 数据库

| 文件 | 用途 | 管理者 |
|------|------|--------|
| `data/checkpoints.db` | 完整对话状态（消息、工具调用、结果） | LangGraph SqliteSaver |
| `data/hyperagent.db` | 业务数据：Event 表 | SQLAlchemy |

两个数据库职责完全分离，互不干扰。

### LangChain 工具模式

工具定义在 `app/agent/tools.py`。每个工具是一个 `@tool` 装饰的函数，内部调用 `ScheduleRepository`。**docstring 必须中英双语**，并包含中文触发短语，确保 DeepSeek 能根据中文输入正确选择工具。所有工具注册在 `ALL_TOOLS` 列表中。添加新工具遵循相同模式：

```python
@tool
def new_tool(param: str) -> str:
    """中文描述。English description.
    触发短语："加xxx""查xxx"...
    """
    # 调用业务逻辑，返回字符串
```

### 中文日期解析

`_preprocess_chinese_time()` 先将"点/半/分"中文表达转换为 `HH:MM` 格式，再交给 `dateparser` 解析。此函数位于 `app/agent/tools.py`，所有涉及时间的工具共用。

### 前端路由

Vue Router 有两个视图：`/`（ChatView 对话页）和 `/calendar`（CalendarView 日程页）。

- **开发模式**：Vite 开发服务器（5173）通过 `vite.config.ts` 中的 proxy 配置将 `/api` 请求转发到 FastAPI（8000）。
- **生产模式**：FastAPI 挂载 `frontend/dist/assets/` 到 `/assets`，并用一条 catch-all 路由返回 `index.html` 实现 SPA 回退。两个模式 API 代码不变。

### ScheduleRepository 双会话模式

`ScheduleRepository` 构造函数接受可选的 `Session` 参数。传入时（如 FastAPI 依赖注入或测试夹具）使用该会话；不传时自动从 `SessionLocal` 新建。测试通过 `conftest.py` 传入内存 SQLite 会话。

### 配置

`app/config.py` 中的 `pydantic-settings` 从 `.env` 读取环境变量。默认模型 `deepseek-v4-flash`。单例 `settings` 实例被全后端引用。

## 添加新功能

1. 在 `app/<domain>/` 下创建领域包（模型、仓库等）
2. 在 `app/agent/tools.py` 中添加 `@tool` 函数，并追加到 `ALL_TOOLS`
3. 在 `app/api/<domain>.py` 中添加 REST 路由，在 `app/main.py` 中注册
4. 可选：在 `app/agent/prompts.py` 中描述新能力
5. 在 `tests/` 中添加测试
