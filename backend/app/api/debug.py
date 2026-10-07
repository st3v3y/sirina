from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException

from ..runtime import runtime

router = APIRouter(prefix="/api/_debug", tags=["debug"])


def _load_wav_as_mono_16k(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(n)
    if sw != 2:
        raise HTTPException(400, "wav must be 16-bit PCM")
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 2:
        pcm = pcm.reshape(-1, 2).mean(axis=1)
    if sr != 16000:
        from ..audio.wav import resample_to_16k

        pcm = resample_to_16k(pcm, sr).astype(np.float32)
    return pcm


@router.get("/diarization-check")
def diarization_check() -> dict[str, str | bool]:
    """Can this build split speakers? (speech helper present and SpeakerKit available)."""
    from ..transcribe.speech_helper import helper_path, probe

    caps = probe(refresh=True)
    if caps.get("speakerkit"):
        return {"ok": True, "detail": f"SpeakerKit available via {helper_path()}"}
    return {"ok": False, "detail": "speech helper missing or not runnable on this Mac"}


@router.get("/transcribe-wav")
async def transcribe_wav(path: str) -> dict[str, str]:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise HTTPException(404, f"file not found: {p}")
    if runtime.whisper is None or not runtime.whisper.is_loaded():
        raise HTTPException(503, "whisper not loaded yet")
    pcm = _load_wav_as_mono_16k(p)
    text = await runtime.whisper.transcribe(pcm)
    return {"path": str(p), "text": text}
