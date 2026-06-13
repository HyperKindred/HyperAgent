# 🤖 HyperAgent

个人 AI 助手 —— 基于 LangGraph + DeepSeek V4 Flash，支持自然语言日程管理。

## 技术栈

| 层 | 技术 |
|---|------|
| LLM | DeepSeek V4 Flash |
| Agent | LangGraph (`create_react_agent`) |
| 记忆 | SQLite (SqliteSaver + SQLAlchemy) |
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

- 📅 自然语言日程管理（"明天下午3点开会"）
- 💬 中文对话，时间感知
- 🧠 对话记忆持久化（重启不丢）
- 🔍 日程搜索与日历视图

## 测试

```bash
uv run pytest
```
