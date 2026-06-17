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

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b-instruct"

    diarization_enabled: bool = False
    hf_token: str = ""  # HuggingFace read token (gates the one-time pyannote download)
    diarization_model: str = "pyannote/speaker-diarization-community-1"

    db_path: str = "./data/transcripts.db"
    app_password: str = ""

    @property
    def db_url(self) -> str:
        path = Path(self.db_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"


settings = Settings()
