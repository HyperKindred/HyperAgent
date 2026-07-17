# AGENTS.md

HyperAgent v0.2.2 repository guide. This file is tracked so contributors and
coding agents use the same current architecture. When this guide conflicts with
executable code or tests, follow the code and tests, then update this guide.

## Commands

Backend:

    uv sync
    uv run pytest -q
    uv run pytest --collect-only -q
    uv run uvicorn app.main:app --port 8000 --reload

Frontend:

    cd frontend && npm install
    cd frontend && npm run dev
    cd frontend && npx vue-tsc --noEmit
    cd frontend && npm run build

Electron and portable build:

    cd frontend && npm run electron:dev
    cd frontend && npm run dist
    build-portable.bat --no-pause

Standard regression:

    uv run pytest -q && cd frontend && npx vue-tsc --noEmit && npm run build

The current backend regression count is 217 tests. Run focused tests first, then
the standard regression for changes to shared behavior, settings, persistence,
or packaging.

## Project Shape

- The repository root is the Python project and Git root.
- frontend/ is an independent Vue, Vite, and npm project.
- electron/ contains Electron main-process resources.
- app/ contains the FastAPI and LangGraph backend.
- data/ is ignored development runtime data.
- Packaged builds use HYPERAGENT_DATA_DIR to store data in
  %APPDATA%/HyperAgent/, preserving user data across updates.

## Runtime Configuration

HyperAgent uses OpenAI-compatible APIs. Current defaults are:

| Setting | Default |
| --- | --- |
| Provider | my_jarvis |
| LLM Base URL | https://api.aijws.com/v1 |
| Chat model | gpt-5.6-terra |
| Vision | Reuses the chat model by default |
| Embedding mode | auto |
| Embedding fallback | OpenRouter qwen/qwen3-embedding-8b |

Configuration precedence is built-in defaults, then development .env, then
settings.json in the active data directory. API keys are never stored in
settings.json. On Windows they live in Windows Credential Manager. A key cleared
in Settings is explicitly disabled so an old .env value cannot reactivate.

- .env is development compatibility only. Packaged builds must not include or
  discover a developer .env file.
- .env.example is a key-free development template.
- Never commit, log, return, export, or test with a real API key.
- GET /api/settings returns key configuration state only, never key values.
- PUT /api/settings atomically updates preferences and credentials, resets
  model and embedding caches, reschedules recurring reminders after timezone
  changes, and queues embedding rebuilds after effective embedding changes.

## Backend Architecture

Chat flow:

    ChatView -> POST /api/chat/stream -> stream_agent()
             -> LangGraph create_react_agent + ChatOpenAI
             -> SSE tokens -> frontend ReadableStream

- app/agent/graph.py rebuilds the agent each turn so the system prompt stays
  current while safely reusing the LLM client and SQLite checkpointer.
- Images use the configured vision model, or the chat model when
  vision_use_same_model is enabled.
- Files are parsed before agent invocation by app/file_parser/parser.py; file
  parsing is not a LangChain tool.
- Missing LLM configuration must return an actionable setup response.
- Stream failures must use safe public errors and propagate client cancellation.

app/agent/tools.py registers 30 LangChain tools. New tools need Chinese and
English docstrings, explicit ALL_TOOLS registration, prompt guidance where
needed, and focused tests. Tool groups cover schedule/time, web search, memory,
reminders, weather/calculation/timezone, GitHub, Notion, and QQ mail.

## Persistence and Time

| Database | Purpose |
| --- | --- |
| hyperagent.db | Events, memories, reminders, threads, notifications |
| checkpoints.db | LangGraph conversation state via SqliteSaver |

Do not merge these databases or delete checkpoints through raw filesystem
operations. Use repository APIs and preserve current session ownership patterns.

All database timestamps are naive UTC. Use helpers in app/utils/time.py:
now(), ensure_utc(), from_local(), to_local(), local_date_bounds(), and
serialize_utc(). Browser calendar values are interpreted in the configured
application timezone and converted to UTC at the API boundary.

## Memory and Embeddings

- Vectors record provider fingerprint, model, and dimensions.
- Semantic retrieval compares only vectors with the current fingerprint and
  matching dimensions; it otherwise falls back to keyword retrieval.
- Changing embedding configuration keeps old vectors but queues a background
  reindex. A second configuration change during reindex queues another pass.
- Auto mode probes the chat provider first, then uses the separately configured
  fallback. Embedding failure must not prevent narrative memory from being saved.
- Memory import and export contain narrative records only; vectors are rebuilt
  for the active provider.

## Reminders

Recurring reminders use timezone-aware CronTrigger values and persist their next
UTC occurrence after firing. A timezone change rebuilds pending recurring jobs.
Keep scheduler lifecycle and safety-scan tests passing when changing this code.

## REST API

All routes are mounted below /api.

| Area | Routes |
| --- | --- |
| Chat | POST /chat, POST /chat/stream |
| Settings | GET/PUT /settings, POST /settings/models, POST /settings/test, GET/POST /settings/embedding/reindex |
| Memory | CRUD /memories, GET /memories/export, POST /memories/import |
| Events | CRUD /events, including date and month filtering |
| Reminders | CRUD /reminders, /reminders/{id}/cancel, /notifications/stream |
| Threads | CRUD /threads, /threads/{id}/messages, /threads/{id}/export |
| Health | GET /health, GET /health/debug |

New endpoints must be registered in app/main.py, validate input with Pydantic,
avoid returning secrets, and receive API tests when changing user data or runtime
configuration.

## Frontend

- Vite serves port 5174 and proxies /api to loopback port HYPERAGENT_PORT
  (default 8000).
- Electron development uses backend port 18080.
- Vue routes are /, /calendar, /settings, and /memory.
- The route guard redirects users without valid LLM configuration to Settings.
- SettingsView supports provider presets, model discovery, manual model IDs with
  suggestions, credential state, capability tests, and reindex progress.
- MemoryView manages narrative memory CRUD and JSON import/export.
- Sanitize LLM markdown with DOMPurify before v-html.
- Per-thread chat localStorage is debounced and must not contain image base64 or
  uploaded file contents.

## Packaging and Releases

build-portable.bat --no-pause is the supported Windows portable build:

1. Builds the frontend.
2. Copies only .env.example into backend resources and removes any .env.
3. Builds the PyInstaller backend and copies a clean frontend dist directory.
4. Packages Electron with .env excluded from extraResources.
5. Produces electron-dist/HyperAgent/ when an earlier output is not in use.

Do not force-delete an in-use portable output. Close the running app first, or
use a separate versioned directory for release verification. Before a release,
verify that the archive contains the frontend index, backend EXE, one frontend
dist tree, and no real .env or plaintext key. Start the packaged backend on an
isolated loopback port and check /api/health reports the release version.

Keep version changes synchronized across pyproject.toml, uv.lock,
frontend/package.json, frontend/package-lock.json, app/main.py,
build-portable.bat, README release text, Git tag, and Release asset name.

## Change Checklist

1. Read surrounding code and preserve user changes.
2. Prefer existing repository, service, and frontend patterns.
3. Add or update tests in proportion to the behavior changed.
4. Run focused tests, then standard regression for shared changes.
5. Update README, .env.example, DEVELOPMENT_PLAN.md, and this file when public
   behavior, configuration, test count, or delivery process changes.
6. Keep credentials, generated data, build artifacts, and local-only files out
   of Git.
