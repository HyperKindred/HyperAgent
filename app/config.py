from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DeepSeek / LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-flash"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # Storage
    data_dir: Path = Path("data")
    database_url: str = "sqlite:///data/hyperagent.db"
    checkpoint_url: str = "sqlite:///data/checkpoints.db"

    # Timezone
    timezone: str = "Asia/Shanghai"

    # Memory management — cap conversation history sent to the LLM.
    # How many past messages to keep (not counting the system prompt).
    # Set to 0 to disable trimming (keep everything forever).
    max_history_messages: int = 40

    # Logging
    log_level: str = "INFO"


settings = Settings()
