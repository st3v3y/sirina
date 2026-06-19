import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> list[str]:
    """Read .env from the cwd (dev) and from APP_DATA_DIR (the packaged app, which has
    no project .env) — the latter wins, so a user can drop a .env in
    ~/Library/Application Support/<app>/ to set OLLAMA_MODEL, HF_TOKEN, etc."""
    files = [".env"]
    app_data = os.environ.get("APP_DATA_DIR", "")
    if app_data:
        files.append(str(Path(app_data).expanduser() / ".env"))
    return files


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    whisper_model: str = "medium"
    whisper_compute_type: str = "int8"
    whisper_language: str = ""
    whisper_initial_prompt: str = ""
    # Greedy (1) is fastest; higher trades speed for marginal accuracy.
    whisper_beam_size: int = 1
    # 0 = auto (use all CPU cores). CTranslate2 is CPU-only on Apple Silicon.
    whisper_cpu_threads: int = 0
    # Transcription engine: auto | faster-whisper | mlx. `auto` uses the Apple-GPU
    # MLX engine on Apple Silicon when available, else faster-whisper (CPU).
    transcription_engine: str = "auto"
    # Override the MLX model repo; empty maps whisper_model → mlx-community/whisper-<size>.
    mlx_whisper_repo: str = ""
    # Rough compute-seconds per audio-second, used to estimate a progress % for
    # engines that don't stream progress (MLX) when chunking is off. Tune if the
    # bar runs fast/slow.
    transcribe_rt_factor: float = 0.4
    # Window size (seconds) for chunked transcription on non-streaming engines
    # (MLX): yields a real progress fraction. 0 disables chunking (single pass).
    transcribe_chunk_seconds: int = 180
    # A track whose peak amplitude is below this (0..1) is treated as silent and
    # skipped — MLX/Whisper hallucinates ("Thanks for watching.") on silence and
    # has no VAD. Real speech peaks far above this; 0 disables the gate.
    silence_peak_threshold: float = 0.005

    # DEV mode: verbose DEBUG logging (set DEV=1).
    dev: bool = False

    # Pluggable LLM provider (see app/llm/provider.py). The default is the local Ollama
    # preset, so an out-of-the-box install talks to a local Ollama exactly as before.
    llm_provider: str = "ollama"  # ollama | lmstudio | openai | google | groq | custom
    llm_model: str = "llama3.1:8b-instruct"
    llm_base_url: str = ""  # overrides the preset base URL (required for `custom`)
    llm_api_key: str = ""  # required for cloud providers
    # Approx. tokens of context the AI model can use; sizes how much transcript the
    # cross-recording chat sends. Match your model's (or Ollama's) configured window.
    llm_context_tokens: int = 8192

    diarization_enabled: bool = False
    hf_token: str = ""  # HuggingFace read token (gates the one-time pyannote download)
    diarization_model: str = "pyannote/speaker-diarization-community-1"

    db_path: str = "./data/transcripts.db"

    # Path to the native macOS system-audio capture sidecar (set by the Tauri app).
    # Empty → fall back to a dev build path; absent → native capture unavailable.
    system_audio_sidecar: str = ""

    # Base directory for the DB, per-recording audio, and model caches. When set
    # (e.g. the packaged desktop app points it at ~/Library/Application Support/<app>),
    # the DB and recordings live under it. Empty → the dev default (./data).
    app_data_dir: str = ""

    @property
    def data_dir(self) -> Path:
        if self.app_data_dir:
            return Path(self.app_data_dir).expanduser().resolve()
        return Path(self.db_path).resolve().parent

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def db_file(self) -> Path:
        # A custom DB_PATH wins; otherwise the DB lives in the data dir (so setting
        # APP_DATA_DIR alone relocates everything together).
        if self.app_data_dir and self.db_path == "./data/transcripts.db":
            return self.data_dir / "transcripts.db"
        return Path(self.db_path).resolve()

    @property
    def db_url(self) -> str:
        path = self.db_file
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"


settings = Settings()


def configure_model_caches() -> None:
    """Point HuggingFace model caches (used by faster-whisper, mlx-whisper, pyannote)
    at the app data dir so the packaged app caches models outside its bundle. Respects
    an already-set HF_HOME. Safe to call once at startup, before any model import."""
    if not settings.app_data_dir:
        return
    hf = settings.data_dir / "models" / "hf"
    hf.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf))


configure_model_caches()
