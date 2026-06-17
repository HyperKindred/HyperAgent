# 🤖 HyperAgent

智能个人 AI 助手 —— 基于 LangGraph + DeepSeek V4 Flash，支持日程管理、RAG 语义记忆、逐 token 流式对话、**GitHub / Notion / QQ 邮箱三方集成**，带 Electron 桌面应用。

## 功能

- 🎯 **流式对话** — SSE 逐 token 响应，文字逐字出现
- 📅 **日程管理** — 自然语言 CRUD（"明天下午3点开会"），日历视图
- 🧠 **RAG 语义记忆** — 自动记住你的信息，语义搜索而非关键词匹配
- 🔔 **定时提醒** — 到点弹窗通知，支持周期性提醒
- ☁️ **天气查询** — 实时天气、温度、风速
- 🧮 **计算与换算** — 数学运算 + 单位换算（公里↔英里、摄氏度↔华氏度等）
- 🌐 **联网搜索** — DuckDuckGo → Bing 多后端兜底，自动抓取内容摘要
- 🖼️ **多模态图片** — 上传/粘贴图片，由视觉模型理解分析
- 📎 **文件上传** — 解析 PDF / Word / TXT 等文件内容
- 🐙 **GitHub 集成** — 查通知、搜 issue/PR、创建 issue
- 📝 **Notion 集成** — 搜索/读取/创建页面，查询数据库
- 📧 **QQ 邮箱** — 收发邮件，按主题搜索
- 🖥️ **Electron 桌面** — 系统托盘 + 原生通知 + 窗口管理

## 技术栈

| 层 | 技术 |
|---|------|
| LLM 推理 | DeepSeek V4 Flash（OpenCode） |
| 视觉理解 | Kimi K2.6（OpenCode） |
| Agent 框架 | LangGraph `create_react_agent`（30 个工具） |
| 向量记忆 | SQLite + OpenRouter Embedding API（RAG 语义搜索） |
| 对话持久化 | LangGraph SqliteSaver |
| 后端 | FastAPI（123 个测试） |
| 前端 | Vue 3 + Vite + TypeScript |
| 桌面 | Electron（系统托盘 + 原生通知） |
| 数据库 | SQLite（SQLAlchemy ORM） |
| 时间解析 | dateparser + 中文时间预处理 |

## 快速开始

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env，填入 API Key 和第三方服务 Token
```

### 2. 安装

```bash
uv sync
cd frontend && npm install && cd ..
```

### 3. 运行

**开发模式（Web）：**
```bash
# 终端 1：后端
uv run uvicorn app.main:app --port 8000 --reload

# 终端 2：前端
cd frontend && npm run dev
```
打开 http://localhost:5173

**Electron 桌面应用：**
```bash
cd frontend && npm run electron:dev
```

**CLI 模式：**
```bash
uv run python main.py
```

### 4. 测试

```bash
uv run pytest -v        # 124 个测试
```

## 项目结构

```
app/
├── agent/              # LangGraph agent
│   ├── graph.py        # Agent 构建、流式与非流式调用
│   ├── tools.py        # 30 个 @tool 工具函数
│   └── prompts.py      # 系统提示词（含时间/记忆注入）
├── memory/             # RAG 个人记忆系统
├── schedule/           # 日程管理域
├── reminder/           # 定时提醒
├── thread/             # 多线程对话
├── github/             # GitHub 集成
├── notion/             # Notion 集成
├── email/              # QQ 邮箱集成
├── weather/            # 天气查询
├── calculator/         # 计算器/单位换算
├── web_search/         # 联网搜索（DuckDuckGo → Bing）
├── api/                # REST 接口
│   ├── chat.py         # POST /api/chat（非流式）+ /api/chat/stream（SSE 流式）
│   ├── schedule.py     # CRUD /api/events
│   ├── reminder.py     # CRUD /api/reminders
│   └── thread.py       # CRUD /api/threads
└── main.py             # FastAPI 入口
electron/               # Electron 桌面应用
  └── main.js           # 主进程（系统托盘 + 后端进程管理）
frontend/
├── src/
│   ├── api/client.ts   # API 客户端 + SSE 流式消费
│   ├── views/          # ChatView 对话页 + CalendarView 日程页
│   ├── store/          # 响应式状态管理
│   └── components/     # 侧边栏 + 通知组件
└── ...
```

## 数据流

```
用户输入 → ChatView.vue
          │
          ├─ POST /api/chat/stream（流式，默认）
          │      → stream_agent()
          │         → agent.astream_events(version="v2")
          │            → 逐 token SSE → ReadableStream → Vue 响应式更新
          │
          └─ POST /api/chat（非流式，后备）
                 → run_agent() → agent.invoke()

LangGraph agent 内部（30 个工具）：
├── ChatOpenAI（streaming=True）
├── 日程 CRUD（7 个） / 提醒（3 个）/ 搜索（1 个）/ 记忆（3 个）
├── 天气 / 计算器 / 时区（3 个）
├── GitHub（5 个）/ Notion（4 个）/ QQ 邮箱（4 个）
├── RAG 记忆注入（系统提示词）
└── SqliteSaver（checkpoints）
```

## 配置参考

| 环境变量 | 用途 |
|---------|------|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 聊天推理 API |
| `VISION_MODEL` | 多模态模型 |
| `EMBEDDING_*` | 向量化记忆 RAG |
| `GITHUB_TOKEN` | GitHub Personal Access Token |
| `NOTION_TOKEN` | Notion Integration Token |
| `QQ_EMAIL_ADDRESS` / `QQ_EMAIL_AUTH_CODE` | QQ 邮箱授权码 |
| `WEATHER_API_KEY` | OpenWeatherMap API Key |
| `TIMEZONE` | 时区（默认 Asia/Shanghai） |
