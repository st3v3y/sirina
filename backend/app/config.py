from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_token: str = ""
    discord_guild_id: str = ""

    whisper_model: str = "medium"
    whisper_compute_type: str = "int8"
    whisper_language: str = ""
    whisper_initial_prompt: str = ""

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b-instruct"

    aspects_interval_seconds: int = 60
    chunk_max_seconds: int = 8
    chunk_silence_ms: int = 600

    db_path: str = "./data/transcripts.db"
    app_password: str = ""

    @property
    def db_url(self) -> str:
        path = Path(self.db_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"


settings = Settings()
