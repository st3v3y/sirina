"""Speech model manager: list, install, and delete on-demand models.

Models are never bundled. They download from Hugging Face into the app's model cache
(`HF_HOME/hub`, under the data dir in the packaged app) and are reused afterwards. A
model counts as installed only when every required file is present, so an interrupted
download never looks usable. Cached models that no feature uses any more (e.g. the old
`medium` or pyannote models) are listed too, so their space can be reclaimed.

The Apple on-device speech asset (draft + captions) is managed by macOS; we only report
its status and ask the helper to install it.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    engine: str  # whisperkit | faster-whisper | speakerkit | apple
    repo: str | None  # Hugging Face repo, None for the Apple asset
    approx_mb: int
    subdir: str | None = None  # folder inside the snapshot (multi-variant repos)
    allow_patterns: tuple[str, ...] | None = None
    required: tuple[str, ...] = field(default_factory=tuple)  # paths relative to the model folder


WHISPERKIT_TURBO = ModelSpec(
    id="whisperkit-large-v3-turbo",
    name="Large v3 Turbo (WhisperKit, Neural Engine)",
    engine="whisperkit",
    repo="argmaxinc/whisperkit-coreml",
    approx_mb=630,
    subdir="openai_whisper-large-v3-v20240930_626MB",
    allow_patterns=("openai_whisper-large-v3-v20240930_626MB/*",),
    required=("AudioEncoder.mlmodelc", "TextDecoder.mlmodelc", "MelSpectrogram.mlmodelc", "config.json"),
)
SPEAKERKIT = ModelSpec(
    id="speakerkit",
    name="Speaker splitting (SpeakerKit)",
    engine="speakerkit",
    repo="argmaxinc/speakerkit-coreml",
    approx_mb=61,
    required=("speaker_segmenter", "speaker_embedder", "speaker_clusterer"),
)
FASTER_WHISPER_LARGE_V3 = ModelSpec(
    id="faster-whisper-large-v3",
    name="Large v3 (CPU fallback)",
    engine="faster-whisper",
    repo="Systran/faster-whisper-large-v3",
    approx_mb=3100,
    required=("model.bin", "config.json", "tokenizer.json"),
)
APPLE_SPEECH = ModelSpec(
    id="apple-speech",
    name="Draft & live captions (macOS on-device speech)",
    engine="apple",
    repo=None,
    approx_mb=0,
)

REGISTRY: tuple[ModelSpec, ...] = (WHISPERKIT_TURBO, SPEAKERKIT, FASTER_WHISPER_LARGE_V3, APPLE_SPEECH)
BY_ID = {m.id: m for m in REGISTRY}


def hub_dir() -> Path:
    from huggingface_hub import constants

    return Path(constants.HF_HUB_CACHE)


def _repo_dir(repo: str) -> Path:
    return hub_dir() / ("models--" + repo.replace("/", "--"))


def _snapshot(repo: str) -> Path | None:
    snaps = _repo_dir(repo) / "snapshots"
    if not snaps.is_dir():
        return None
    candidates = sorted((p for p in snaps.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def model_dir(spec: ModelSpec) -> Path | None:
    """The folder to hand to the engine, or None when not (fully) installed."""
    if spec.repo is None:
        return None
    snap = _snapshot(spec.repo)
    if snap is None:
        return None
    folder = snap / spec.subdir if spec.subdir else snap
    if not folder.is_dir() or not all((folder / r).exists() for r in spec.required):
        return None
    return folder


def _size_on_disk(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            pass
    return total


# id -> {"state": "downloading" | "failed", "error": str | None}
_installs: dict[str, dict] = {}


def in_use_ids() -> set[str]:
    """Models the current settings rely on."""
    from .config import settings
    from .runtime import runtime

    used: set[str] = set()
    name = getattr(runtime.whisper, "name", "")
    if name == "whisperkit":
        used.add(WHISPERKIT_TURBO.id)
    elif name == "faster-whisper":
        used.add(FASTER_WHISPER_LARGE_V3.id)
    if settings.diarization_enabled:
        used.add(SPEAKERKIT.id)
    return used


def busy() -> bool:
    """True while speech work runs (a job, or transcription during a recording)."""
    from .runtime import runtime

    proc = runtime.processor
    if proc is not None and proc.is_busy():
        return True
    rec = runtime.recorder
    return bool(rec is not None and rec.is_recording() and getattr(rec, "live_finalizing", lambda: False)())


def list_models(apple_installed: bool | None = None) -> list[dict]:
    used = in_use_ids()
    out: list[dict] = []
    known_repos = set()
    for spec in REGISTRY:
        install = _installs.get(spec.id, {})
        if spec.repo is None:
            installed = bool(apple_installed)
            size = 0
        else:
            known_repos.add(spec.repo)
            installed = model_dir(spec) is not None
            size = _size_on_disk(_repo_dir(spec.repo)) if installed else 0
        out.append({
            "id": spec.id,
            "name": spec.name,
            "engine": spec.engine,
            "approx_mb": spec.approx_mb,
            "installed": installed,
            "size_bytes": size,
            "in_use": spec.id in used,
            "state": install.get("state") or ("installed" if installed else "not_installed"),
            "progress": install.get("progress"),
            "error": install.get("error"),
            "managed_by_os": spec.repo is None,
        })
    # Leftover caches (old models no feature uses any more).
    hub = hub_dir()
    if hub.is_dir():
        for d in sorted(hub.glob("models--*")):
            repo = d.name[len("models--"):].replace("--", "/", 1)
            if repo in known_repos:
                continue
            out.append({
                "id": "cache:" + repo,
                "name": repo,
                "engine": "unused",
                "approx_mb": 0,
                "installed": True,
                "size_bytes": _size_on_disk(d),
                "in_use": False,
                "state": "installed",
                "progress": None,
                "error": None,
                "managed_by_os": False,
            })
    return out


def _download(spec: ModelSpec) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(spec.repo, allow_patterns=list(spec.allow_patterns) if spec.allow_patterns else None)


async def install(model_id: str, helper=None) -> None:
    """Download a model in the background; progress is polled via list_models()."""
    spec = BY_ID.get(model_id)
    if spec is None:
        raise KeyError(model_id)
    if _installs.get(model_id, {}).get("state") == "downloading":
        return
    _installs[model_id] = {"state": "downloading", "progress": 0.0, "error": None}

    async def _watch_progress() -> None:
        if spec.repo is None or not spec.approx_mb:
            return
        while _installs.get(model_id, {}).get("state") == "downloading":
            done = _size_on_disk(_repo_dir(spec.repo) / "blobs")
            _installs[model_id]["progress"] = min(0.99, done / (spec.approx_mb * 1024 * 1024))
            await asyncio.sleep(1.0)

    watcher = asyncio.create_task(_watch_progress())
    try:
        if spec.repo is None:
            if helper is None:
                raise RuntimeError("speech helper unavailable")
            from .config import settings

            await helper.request("install_speech_asset", language=settings.whisper_language or "en")
        else:
            await asyncio.to_thread(_download, spec)
            if model_dir(spec) is None:
                raise RuntimeError("download finished but files are missing")
        _installs.pop(model_id, None)
        log.info("model %s installed", model_id)
    except Exception as e:
        log.exception("model %s install failed", model_id)
        _installs[model_id] = {"state": "failed", "progress": None, "error": f"{type(e).__name__}: {e}"}
    finally:
        watcher.cancel()


class InUseError(RuntimeError):
    pass


def delete(model_id: str) -> int:
    """Delete a model's cache. Returns freed bytes. Refuses the in-use model while busy."""
    if model_id.startswith("cache:"):
        repo = model_id[len("cache:"):]
        d = _repo_dir(repo)
    else:
        spec = BY_ID.get(model_id)
        if spec is None or spec.repo is None:
            raise KeyError(model_id)
        if model_id in in_use_ids() and busy():
            raise InUseError("This model is in use by a running transcription. Try again when it finishes.")
        d = _repo_dir(spec.repo)
    # Only ever delete a direct `models--*` child of the cache (no `..` escapes).
    resolved = d.resolve()
    if resolved.parent != hub_dir().resolve() or not resolved.name.startswith("models--") or not d.exists():
        raise KeyError(model_id)
    freed = _size_on_disk(d)
    shutil.rmtree(d, ignore_errors=True)
    _installs.pop(model_id, None)
    log.info("deleted model cache %s (%d bytes)", d.name, freed)
    return freed
