from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    whisper_model: str = "medium"
    whisper_compute_type: str = "int8"
    whisper_language: str = ""
    whisper_initial_prompt: str = ""

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b-instruct"

    db_path: str = "./data/transcripts.db"
    app_password: str = ""

    @property
    def db_url(self) -> str:
        path = Path(self.db_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"


settings = Settings()
