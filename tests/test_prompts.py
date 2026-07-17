"""Runtime prompt preference tests."""

from app.agent import prompts


def test_system_prompt_uses_configured_assistant_style(monkeypatch):
    monkeypatch.setattr(prompts.settings, "assistant_style", "concise")
    monkeypatch.setattr(prompts, "get_memory_context", lambda: None)
    monkeypatch.setattr(prompts, "drain_notifications", lambda: "")

    prompt = prompts.get_system_prompt()

    assert "优先给出结论和必要步骤" in prompt
