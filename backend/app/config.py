import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> list[str]:
    """Read .env from the cwd (dev) and from APP_DATA_DIR (the packaged app, which has
    no project .env) — the latter wins, so a user can drop a .env in
    ~/Library/Application Support/<app>/ to set LLM_MODEL, WHISPER_LANGUAGE, etc."""
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
    # 0 = auto (one thread per performance core on Apple Silicon, else all cores).
    whisper_cpu_threads: int = 0
    # Transcription engine: auto | whisperkit | faster-whisper. `auto` uses WhisperKit
    # (large-v3-turbo on the Neural Engine) on Apple Silicon, else faster-whisper (CPU).
    transcription_engine: str = "auto"
    # Defaults for new recordings (changeable per recording in the start dialog):
    # finalize the transcript during the call (WhisperKit only) / show live captions.
    live_transcribe_default: bool = True
    live_captions_default: bool = False
    # Final transcript is produced in windows of about this many seconds, cut at a pause
    # (both engines). 0 = one window for the whole recording.
    transcribe_chunk_seconds: int = 180
    # A track whose peak amplitude is below this (0..1) is treated as silent and
    # skipped — Whisper hallucinates ("Thanks for watching.") on silence and
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
    # Let "thinking" models (Qwen 3.x, DeepSeek-R1, …) reason before answering (Ollama only).
    # Off by default: qwen3.5:9b spent 120 s and ~2,400 hidden tokens on a one-sentence
    # summary with thinking on, 1.4 s with it off — and the answers were equally good.
    llm_think: bool = False

    # After stopping, offer to trim leading/trailing silence when it totals at least this
    # many seconds (the "forgot to stop the recording" case). 0 disables the prompt.
    silence_trim_min_seconds: float = 60.0

    # Compress a recording's WAV tracks to AAC (.m4a, ~10-15× smaller) once processing
    # finishes, via macOS's built-in `afconvert`. Re-processing transparently decodes
    # them back to WAV first. Disable to keep the original PCM WAVs forever.
    compress_audio: bool = True

    diarization_enabled: bool = False
    # When speakers are split: once after the recording (default) or also during it.
    diarization_timing: str = "after_stop"
    # Auto-link a recording's diarized speakers to known People whose enrolled voice
    # fingerprint is at least this similar (cosine, 0..1). Voiceprints are enrolled by
    # manually renaming a speaker to a person. 0 disables automatic matching.
    # Calibrated on SpeakerKit centroids (2026-10-06, one 2 h call, 5-min stretches): the
    # same person scored 0.92-0.96 across stretches, different people 0.02-0.34.
    voice_match_threshold: float = 0.6
    # Drop a diarized system-track speaker whose speech overlaps the mic ("You") speech
    # by at least this fraction — that's the user's own voice echoing in the call audio,
    # which otherwise shows up as a phantom extra speaker made of fragments the mic
    # already captured properly. 0 disables echo suppression.
    echo_speaker_overlap: float = 0.75

    db_path: str = "./data/transcripts.db"

    # Path to the native macOS system-audio capture sidecar (set by the Tauri app).
    # Empty → fall back to a dev build path; absent → native capture unavailable.
    system_audio_sidecar: str = ""
    # Path to the bundled speech helper (native/speech-engine); empty → dev build location.
    speech_engine_helper: str = ""

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
    """Point HuggingFace model caches (faster-whisper, WhisperKit, SpeakerKit models)
    at the app data dir so the packaged app caches models outside its bundle. Respects
    an already-set HF_HOME. Safe to call once at startup, before any model import."""
    if not settings.app_data_dir:
        return
    hf = settings.data_dir / "models" / "hf"
    hf.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf))


configure_model_caches()
