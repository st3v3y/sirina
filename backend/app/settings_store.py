"""User-editable settings: a registry of editable fields + a service that layers
DB overrides onto the `Settings` singleton.

Effective config is `defaults → .env → DB overrides`. At startup `load_overrides()`
reads the `setting` table and `setattr`s coerced values onto the singleton, so every
existing `settings.X` read site transparently sees overrides. `apply()` validates a
patch against the registry, persists it, and re-applies it live.

Secrets route through the `secret_get`/`secret_set` seam (DB-backed in v1) so an OS
keyring backend can replace the body later without touching call sites.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlmodel import Session, select

from .config import settings
from .db import engine
from .models import Setting

log = logging.getLogger(__name__)

FieldType = Literal["string", "text", "int", "float", "bool", "enum"]
Section = Literal["ai", "transcription", "diarization", "advanced"]
Restart = Literal["none", "reload_engine", "restart_app"]


@dataclass(frozen=True)
class FieldSpec:
    key: str  # must match a `Settings` attribute
    label: str
    section: Section
    type: FieldType
    options: list[str] | None = None
    # Frontend hint: populate this field's dropdown from a dynamic source (e.g.
    # installed Ollama models) rather than a fixed `options` list.
    options_source: str | None = None
    secret: bool = False
    restart: Restart = "none"
    help: str | None = None


# The single source of truth for the Settings UI. Adding a field here is all that's
# needed for it to appear on the page and be writable via the API.
FIELDS: list[FieldSpec] = [
    # --- AI model (pluggable provider; the Settings page renders this section with a
    # provider/model/key/test UI driven by /api/llm/*, but the values persist here) ---
    FieldSpec(
        "llm_provider", "Provider", "ai", "enum",
        options=["ollama", "lmstudio", "openai", "google", "groq", "custom"],
        help="Local (Ollama/LM Studio) or cloud (OpenAI/Google/Groq/custom).",
    ),
    FieldSpec("llm_model", "Model", "ai", "string", help="The chat model for summaries and Q&A."),
    FieldSpec(
        "llm_base_url", "Base URL", "ai", "string",
        help="Override the provider's API base URL (required for custom).",
    ),
    FieldSpec("llm_api_key", "API key", "ai", "string", secret=True,
              help="Required for cloud providers."),
    # --- Transcription ---
    FieldSpec(
        "transcription_engine", "Engine", "transcription", "enum",
        options=["auto", "faster-whisper", "mlx"], restart="reload_engine",
        help="auto = MLX on Apple Silicon, else faster-whisper (CPU).",
    ),
    FieldSpec(
        "whisper_model", "Whisper model", "transcription", "string",
        options=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        restart="reload_engine", help="Larger = more accurate, slower.",
    ),
    FieldSpec(
        "whisper_compute_type", "Compute type", "transcription", "enum",
        options=["int8", "int8_float16", "float16", "float32"], restart="reload_engine",
        help="faster-whisper quantization. int8 is fastest on CPU.",
    ),
    FieldSpec(
        "whisper_language", "Language", "transcription", "string",
        help="Force a language (e.g. en, de). Empty = auto-detect.",
    ),
    FieldSpec(
        "whisper_initial_prompt", "Vocabulary hints", "transcription", "text",
        help="Names/jargon to bias transcription toward (an initial prompt).",
    ),
    FieldSpec("whisper_beam_size", "Beam size", "transcription", "int", help="1 = greedy (fastest)."),
    # --- Speaker diarization ---
    FieldSpec("diarization_enabled", "Enable diarization", "diarization", "bool"),
    FieldSpec("hf_token", "HuggingFace token", "diarization", "string", secret=True,
              help="Read token gating the one-time pyannote download."),
    FieldSpec(
        "diarization_model", "Diarization model", "diarization", "string",
        options=[
            "pyannote/speaker-diarization-community-1",
            "pyannote/speaker-diarization-3.1",
        ],
        help="pyannote pipeline.",
    ),
    # --- Advanced ---
    FieldSpec("transcribe_chunk_seconds", "Chunk seconds", "advanced", "int",
              help="Window size for chunked transcription (MLX). 0 disables chunking."),
    FieldSpec("silence_peak_threshold", "Silence threshold", "advanced", "float",
              help="Tracks peaking below this (0..1) are skipped as silent. 0 disables."),
    FieldSpec("whisper_cpu_threads", "CPU threads", "advanced", "int", restart="reload_engine",
              help="0 = use all cores."),
    FieldSpec("llm_context_tokens", "AI context window (tokens)", "advanced", "int",
              help="How much transcript cross-recording chat sends to the AI. Match your model's "
                   "context window (for local Ollama, also its configured num_ctx)."),
]

REGISTRY: dict[str, FieldSpec] = {f.key: f for f in FIELDS}


@dataclass
class ApplyResult:
    reload_required: bool = False
    llm_changed: bool = False


def _coerce(spec: FieldSpec, raw: Any) -> Any:
    """Cast an incoming value (JSON-native or text) to the field's type.
    Raises ValueError on an invalid value (rejected as HTTP 400 by the API)."""
    if spec.type == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if spec.type == "int":
        return int(raw)
    if spec.type == "float":
        return float(raw)
    if spec.type == "enum":
        v = str(raw)
        if v not in (spec.options or []):
            raise ValueError(f"{spec.key}: {v!r} is not one of {spec.options}")
        return v
    return str(raw)  # string | text


def _to_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _persist(session: Session, key: str, text: str) -> None:
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=text))
    else:
        row.value = text
        session.add(row)


# --- Secret seam: OS keyring (macOS Keychain / Windows Cred Manager / Linux Secret
#     Service) with a DB fallback when no keyring backend is available. ---

KEYRING_SERVICE = "sirina"


def _keyring_ok() -> bool:
    """True if a real OS keyring backend is available (not the fail/null backend)."""
    try:
        import keyring
        from keyring.backends.fail import Keyring as _Fail

        return not isinstance(keyring.get_keyring(), _Fail)
    except Exception:
        return False


def secret_get(key: str) -> str:
    """Effective value of a secret (keyring → DB fallback → .env/default). Never returned
    in plaintext by the API — callers only check truthiness."""
    try:
        import keyring

        v = keyring.get_password(KEYRING_SERVICE, key)
        if v:
            return v
    except Exception:
        pass
    with Session(engine) as s:
        row = s.get(Setting, key)
    if row and row.value:
        return row.value
    return str(getattr(settings, key, "") or "")


def secret_set(key: str, value: str, session: Session | None = None) -> None:
    """Store a secret in the OS keyring; fall back to the DB when no backend exists."""
    stored = False
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, key, value)
        stored = True
    except Exception:
        log.warning("keyring unavailable for %r; using DB fallback", key)
    if not stored:
        if session is not None:
            _persist(session, key, value)
        else:
            with Session(engine) as s:
                _persist(s, key, value)
                s.commit()
    setattr(settings, key, value)


def _migrate_secrets_to_keyring() -> None:
    """One-time: move any plaintext secret out of the `setting` table into the keyring."""
    if not _keyring_ok():
        return
    import keyring

    moved = 0
    with Session(engine) as s:
        for key, spec in REGISTRY.items():
            if not spec.secret:
                continue
            row = s.get(Setting, key)
            if row and row.value:
                try:
                    keyring.set_password(KEYRING_SERVICE, key, row.value)
                    s.delete(row)
                    moved += 1
                except Exception:
                    log.warning("could not migrate secret %r to the keyring", key)
        if moved:
            s.commit()
    if moved:
        log.info("migrated %d secret(s) from the database into the OS keyring", moved)


def load_overrides() -> None:
    """Apply persisted overrides onto the `Settings` singleton. Call once at startup,
    after `init_db()` and before the engine/LLM are constructed."""
    _migrate_secrets_to_keyring()
    with Session(engine) as s:
        rows = s.exec(select(Setting)).all()
    by_key = {r.key: r.value for r in rows}
    applied = 0
    for key, spec in REGISTRY.items():
        if spec.secret:
            v = secret_get(key)  # keyring → DB fallback
            if v:
                setattr(settings, key, v)
                applied += 1
        elif key in by_key:
            try:
                setattr(settings, key, _coerce(spec, by_key[key]))
                applied += 1
            except Exception:
                log.warning("ignoring invalid stored setting %s=%r", key, by_key[key])
    if applied:
        log.info("applied %d persisted setting override(s)", applied)


def apply(updates: dict[str, Any]) -> ApplyResult:
    """Validate, persist, and live-apply a patch. Validates the whole patch first, so a
    single bad value rejects the patch without changing anything (prior values retained).
    An empty secret value leaves the existing secret unchanged."""
    staged: list[tuple[FieldSpec, Any, str]] = []
    for key, raw in updates.items():
        spec = REGISTRY.get(key)
        if spec is None:
            raise ValueError(f"unknown setting: {key}")
        if spec.secret:
            if raw is None or str(raw) == "":
                continue  # empty → preserve the existing secret
            value: Any = str(raw)
            staged.append((spec, value, value))
        else:
            value = _coerce(spec, raw)
            staged.append((spec, value, _to_text(value)))

    result = ApplyResult()
    if not staged:
        return result
    with Session(engine) as s:
        for spec, value, text in staged:
            if spec.secret:
                secret_set(spec.key, value, s)
            else:
                _persist(s, spec.key, text)
                setattr(settings, spec.key, value)
            if spec.restart == "reload_engine":
                result.reload_required = True
            if spec.section == "ai":
                result.llm_changed = True
        s.commit()
    return result
