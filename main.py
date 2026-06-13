"""HyperAgent – CLI interactive loop."""

import shutil

from app.agent.graph import build_agent, run_agent
from app.config import settings
from app.schedule.database import init_db


def print_banner():
    terminal_width = shutil.get_terminal_size((80, 20)).columns
    print("=" * terminal_width)
    print("  🤖 HyperAgent – 个人 AI 助手".center(terminal_width))
    print(f"  时区: {settings.timezone}".center(terminal_width))
    print("  输入 /help 查看命令 | /quit 退出".center(terminal_width))
    print("=" * terminal_width)
    print()


def print_help():
    print("""
  ┌─ 命令列表 ─────────────────────────────┐
  │  /quit  或 /exit  退出程序              │
  │  /help  显示此帮助                      │
  │  /clear 清屏                           │
  │  /new   开启新对话（重置上下文）         │
  └─────────────────────────────────────────┘

  💡 日程管理示例：
     "加日程：明天下午3点开会讨论项目"
     "今天有什么安排？"
     "把会议的标题改成'项目评审'"
     "删除 ID 为 1 的日程"
     "搜索跟'会议'有关的日程"
""")


def main():
    init_db()

    # Force agent to build once so the first user message is fast
    print("正在启动 HyperAgent ...")
    build_agent()
    print_banner()

    thread_id = "hyperagent-main"

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd in ("/quit", "/exit"):
                print("👋 再见！")
                break
            elif cmd == "/help":
                print_help()
                continue
            elif cmd == "/clear":
                import os

                os.system("cls" if os.name == "nt" else "clear")
                print_banner()
                continue
            elif cmd == "/new":
                import uuid

                thread_id = f"hyperagent-{uuid.uuid4().hex[:8]}"
                print("🔄 已开启新对话。")
                continue
            else:
                print(f"❌ 未知命令：{cmd}。输入 /help 查看命令列表。")
                continue

        try:
            reply = run_agent(user_input, thread_id=thread_id)
            print(f"\n{reply}\n")
        except Exception as e:
            print(f"\n❌ 出错了：{e}")
            print("    (可能是 API Key 配置问题，请检查 .env 文件)\n")


if __name__ == "__main__":
    main()
