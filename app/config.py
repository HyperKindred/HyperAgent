import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Search
    search_engine_url: str = ""

    # DeepSeek API — legacy, kept for backward compatibility
    # (embedding_* settings below take precedence)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-flash"

    # Embedding API - kept separate because not every chat gateway exposes it.
    embedding_mode: str = "auto"
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_api_key: str = ""
    embedding_model: str = "qwen/qwen3-embedding-8b"
    embedding_auto_model: str = "text-embedding-3-small"

    # LLM API - OpenAI-compatible chat gateway
    provider: str = "my_jarvis"
    llm_base_url: str = "https://api.aijws.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-5.6-terra"
    llm_temperature: float | None = None
    llm_max_tokens: int = 4096
    llm_reasoning_effort: str | None = "none"

    # Vision defaults to the chat model; a separate model remains configurable.
    vision_use_same_model: bool = True
    vision_model: str = ""

    # Storage — data directory for all SQLite databases.
    #
    # In development (``uv run``) this defaults to ``data/`` relative to the
    # project root.  In the packaged Electron build the launcher sets
    # ``HYPERAGENT_DATA_DIR`` to ``app.getPath('userData')``
    # (``%APPDATA%/HyperAgent`` on Windows) so that user data survives
    # version updates.
    data_dir: Path = Path(
        os.environ.get("HYPERAGENT_DATA_DIR", "data")
    )
    database_url: str = ""
    checkpoint_url: str = ""

    @property
    def resolved_database_url(self) -> str:
        """Return the database URL, defaulting to ``data_dir / hyperagent.db``."""
        return self.database_url or f"sqlite:///{self.data_dir / 'hyperagent.db'}"

    @property
    def resolved_checkpoint_url(self) -> str:
        """Return the checkpoint URL, defaulting to ``data_dir / checkpoints.db``."""
        return self.checkpoint_url or f"sqlite:///{self.data_dir / 'checkpoints.db'}"

    # Timezone
    timezone: str = "Asia/Shanghai"

    # Memory management — cap conversation history sent to the LLM.
    # How many past messages to keep (not counting the system prompt).
    # Set to 0 to disable trimming (keep everything forever).
    max_history_messages: int = 40
    assistant_style: str = "balanced"

    # Logging
    log_level: str = "INFO"

    # Weather API (OpenWeatherMap)
    weather_api_key: str = ""
    weather_base_url: str = "https://api.openweathermap.org/data/2.5"

    # GitHub Integration
    github_token: str = ""
    github_username: str = ""

    # Notion Integration
    notion_token: str = ""

    # QQ Email Integration
    qq_email_address: str = ""
    qq_email_auth_code: str = ""


settings = Settings()

# Apply user-facing settings after .env has populated the compatibility layer.
from app.settings.service import runtime_settings  # noqa: E402

runtime_settings.load_into(settings)

