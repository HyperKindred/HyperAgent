# 🤖 HyperAgent

智能个人 AI 助手 —— 基于 LangGraph + DeepSeek V4 Flash，支持日程管理、RAG 语义记忆与自由对话。

## 技术栈

| 层 | 技术 |
|---|------|
| LLM | DeepSeek V4 Flash |
| Agent | LangGraph (`create_react_agent`) |
| 向量记忆 | SQLite + DeepSeek Embedding API（RAG 语义搜索） |
| 对话记忆 | LangGraph SqliteSaver |
| 后端 | FastAPI |
| 前端 | Vue 3 + Vite + TypeScript |
| 桌面 | Electron (计划中) |

## 快速开始

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key
```

### 2. 安装

```bash
uv sync
cd frontend && npm install && cd ..
```

### 3. 运行

**开发模式：**
```bash
# 终端 1：后端
uv run uvicorn app.main:app --port 8000 --reload

# 终端 2：前端
cd frontend && npm run dev
```
打开 http://localhost:5173

**生产模式：**
```bash
uv run uvicorn app.main:app --port 8000   # http://localhost:8000
uv run python main.py                     # CLI 模式
```

## 功能

- 📅 **日程管理** — 自然语言创建/查询/修改/删除日程（"明天下午3点开会"）
- 🧠 **RAG 语义记忆** — 自动记住对话中分享的个人信息，语义搜索而非关键词匹配。记过"最近开始学吉他"，搜"最近在忙什么"也能找到。
- 💬 **自由对话** — 闲聊、共情、给建议，不局限于日程操作
- 🕐 **时间感知** — 中文时间解析（"后天上午10点"），每次对话注入当前时间
- 🔍 **日历视图** — 前端日历页面，支持日程增删改查
- 🗂️ **笔记与待办** — 计划中

## 项目结构

```
app/
├── agent/          # LangGraph agent + 9 个工具 + 系统提示词
│   ├── graph.py    # Agent 构建与调用
│   ├── tools.py    # 9 个 @tool 工具函数（日程6 + 记忆3）
│   └── prompts.py  # 系统提示词（含时间/记忆注入）
├── memory/         # RAG 个人记忆系统
│   ├── models.py   # Memory ORM + Pydantic schema
│   ├── embeddings.py  # DeepSeek Embedding API + 余弦相似度
│   ├── repository.py  # 语义搜索仓库
│   └── context.py     # 记忆注入系统提示词
├── schedule/       # 日程管理域
│   ├── models.py   # Event ORM + Pydantic schema
│   ├── repository.py  # CRUD 仓库
│   └── notifier.py    # 日历操作通知
├── api/            # REST 接口
│   ├── chat.py     # POST /api/chat
│   └── schedule.py # CRUD /api/events
└── main.py         # FastAPI 入口
```

## 测试

```bash
uv run pytest        # 39 个测试
uv run pytest -v     # 详细输出
```
