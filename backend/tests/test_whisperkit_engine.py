"""WhisperKit engine + speech helper client against a fake JSON-lines helper."""
from pathlib import Path

import pytest
from tests.conftest import exec_wrapper

from app import speech_models
from app.transcribe import engine as engine_mod
from app.transcribe.speech_helper import HelperError, SpeechHelper
from app.transcribe.whisperkit import WhisperKitEngine

FAKE = str(Path(__file__).parent / "fixtures" / "fake_speech_engine.py")


@pytest.fixture()
def helper(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_HELPER_STATE", str(tmp_path / "crashed"))
    h = SpeechHelper(exec_wrapper(tmp_path, "speech-engine", FAKE), timeout_s=10)
    yield h


@pytest.fixture()
def installed(tmp_path, monkeypatch):
    folder = tmp_path / "wk"
    folder.mkdir()
    monkeypatch.setattr(speech_models, "model_dir", lambda spec: folder)
    return folder


@pytest.mark.asyncio
async def test_window_times_are_absolute(helper, installed):
    eng = WhisperKitEngine(helper=helper)
    await eng.load()
    lines, lang = await eng.transcribe_window("/x.wav", 180.0, 360.0, language="en")
    assert lang == "en"
    assert [(ln.start, ln.end) for ln in lines] == [(181.0, 359.0)]
    assert lines[0].words[0] == (181.0, 182.0, "hello")
    await helper.close()


@pytest.mark.asyncio
async def test_restart_once_and_reload_models(helper, installed):
    eng = WhisperKitEngine(helper=helper)
    await eng.load()
    resp = await helper.request("crash_once")  # first attempt kills the helper
    assert resp["survived"] is True
    # The restart re-sent load_whisper, so transcription still works.
    lines, _ = await eng.transcribe_window("/x.wav", 0.0, 20.0)
    assert lines and lines[0].text == "hello world"
    await helper.close()


@pytest.mark.asyncio
async def test_helper_errors_are_raised(helper, installed):
    with pytest.raises(HelperError, match="not loaded"):
        await helper.request("transcribe", path="/x.wav", start_s=0, end_s=5)
    await helper.close()


@pytest.mark.asyncio
async def test_missing_model_download_failure_is_raised(helper, monkeypatch):
    monkeypatch.setattr(speech_models, "model_dir", lambda spec: None)

    async def fail_install(model_id, helper=None):
        speech_models._installs[model_id] = {"state": "failed", "error": "offline"}

    monkeypatch.setattr(speech_models, "install", fail_install)
    eng = WhisperKitEngine(helper=helper)
    with pytest.raises(RuntimeError, match="offline"):
        await eng.load()
    assert not eng.is_loaded() and not eng.preparing
    await helper.close()


def test_selection_falls_back_with_reason(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "transcription_engine", "auto")
    monkeypatch.setattr(engine_mod, "_whisperkit_unavailable_reason", lambda: "no helper")
    from app.runtime import runtime

    e = engine_mod.select_engine()
    assert e.name == "faster-whisper" and runtime.engine_note == "no helper"


def test_selection_prefers_whisperkit_and_maps_mlx_to_auto(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "transcription_engine", "mlx")
    monkeypatch.setattr(engine_mod, "_whisperkit_unavailable_reason", lambda: None)
    assert engine_mod.select_engine().name == "whisperkit"
    monkeypatch.setattr(settings, "transcription_engine", "faster-whisper")
    assert engine_mod.select_engine().name == "faster-whisper"
