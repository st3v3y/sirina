"""Fast on-device draft transcription (Apple SpeechTranscriber via the speech helper).

Lower quality than the final pass but ~65x faster than real time, so a readable draft
exists right after a recording stops; the final pass then replaces it window by window."""
from __future__ import annotations

from ..config import settings
from .speech_helper import SpeechHelper, probe, shared_helper
from .whisper import TLine


def make_drafter(helper: SpeechHelper | None = None):
    """An async drafter for the job, or None when on-device speech isn't available
    (macOS < 26, helper missing)."""
    if not probe().get("apple_speech"):
        return None
    h = helper or shared_helper()

    async def draft(path: str, start_s: float, end_s: float | None, language: str | None) -> list[TLine]:
        resp = await h.request(
            "draft", path=path, start_s=start_s, end_s=end_s,
            language=language, prompt=settings.whisper_initial_prompt or None,
        )
        return [
            TLine(float(seg["start"]), float(seg["end"]), str(seg["text"]).strip())
            for seg in resp.get("segments") or []
            if str(seg.get("text", "")).strip()
        ]

    return draft
