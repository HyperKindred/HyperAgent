"""
HyperAgent 后端启动入口（PyInstaller 专用）

打包为独立 exe 后，Electron 主进程通过子进程调用此 exe 启动后端。
"""
import os
import sys

# ── 切换到 exe 所在目录 ────────────────────────────────────
if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
else:
    exe_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(exe_dir)

# Development keeps legacy ``.env`` compatibility. A packaged backend must
# never walk out of its resource directory: a build located under a source
# checkout could otherwise inherit the developer's credentials.
if not getattr(sys, "frozen", False):
    _env_found = False
    _search_dir = exe_dir
    for _ in range(5):
        if os.path.isfile(os.path.join(_search_dir, ".env")):
            os.chdir(_search_dir)
            _env_found = True
            break
        _search_dir = os.path.dirname(_search_dir)
    if not _env_found:
        print("[backend] WARNING: .env not found — configure models in Settings")
else:
    print("[backend] Packaged mode: using the in-app settings store")

# ── 确保能找到项目模块 ──────────────────────────────────────
if getattr(sys, "frozen", False):
    base = sys._MEIPASS
    if base not in sys.path:
        sys.path.insert(0, base)

import uvicorn
from app.main import app  # noqa: E402 — 需要在 sys.path 设置后导入

if __name__ == "__main__":
    port = int(os.environ.get("HYPERAGENT_PORT", 18080))
    host = os.environ.get("HYPERAGENT_HOST", "127.0.0.1")

    print(f"[backend] Starting HyperAgent backend on {host}:{port}")
    sys.stdout.flush()

    uvicorn.run(
        app,                     # FastAPI 实例，而非字符串
        host=host,
        port=port,
        log_level="info",
        reload=False,
        workers=1,
        access_log=False,
    )
