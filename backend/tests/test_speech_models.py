"""Model manager: install status from required files, leftovers listed, delete guards."""
from pathlib import Path

import pytest

from app import speech_models as sm


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "hub_dir", lambda: tmp_path)
    monkeypatch.setattr(sm, "in_use_ids", lambda: set())
    monkeypatch.setattr(sm, "busy", lambda: False)
    from app import osinfo

    monkeypatch.setattr(osinfo, "platform_name", lambda: "macos")
    sm._installs.clear()
    return tmp_path


def _make(hub: Path, repo: str, files: list[str]) -> Path:
    snap = hub / ("models--" + repo.replace("/", "--")) / "snapshots" / "abc"
    for f in files:
        p = snap / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * 10)
    return snap


def test_partial_download_is_not_installed(hub):
    _make(hub, "argmaxinc/whisperkit-coreml", ["openai_whisper-large-v3-v20240930_626MB/AudioEncoder.mlmodelc"])
    assert sm.model_dir(sm.WHISPERKIT_TURBO) is None


def test_complete_model_is_installed(hub):
    files = [f"openai_whisper-large-v3-v20240930_626MB/{r}" for r in sm.WHISPERKIT_TURBO.required]
    snap = _make(hub, "argmaxinc/whisperkit-coreml", files)
    assert sm.model_dir(sm.WHISPERKIT_TURBO) == snap / "openai_whisper-large-v3-v20240930_626MB"
    row = next(m for m in sm.list_models() if m["id"] == sm.WHISPERKIT_TURBO.id)
    assert row["installed"] and row["size_bytes"] > 0


def test_leftover_cache_listed_and_deletable(hub):
    _make(hub, "Systran/faster-whisper-medium", ["model.bin"])
    rows = {m["id"]: m for m in sm.list_models()}
    assert rows["cache:Systran/faster-whisper-medium"]["engine"] == "unused"
    freed = sm.delete("cache:Systran/faster-whisper-medium")
    assert freed == 10
    assert not (hub / "models--Systran--faster-whisper-medium").exists()


def test_delete_in_use_refused_while_busy(hub, monkeypatch):
    _make(hub, "argmaxinc/speakerkit-coreml", list(sm.SPEAKERKIT.required))
    monkeypatch.setattr(sm, "in_use_ids", lambda: {sm.SPEAKERKIT.id})
    monkeypatch.setattr(sm, "busy", lambda: True)
    with pytest.raises(sm.InUseError):
        sm.delete(sm.SPEAKERKIT.id)
    monkeypatch.setattr(sm, "busy", lambda: False)
    assert sm.delete(sm.SPEAKERKIT.id) > 0


def test_delete_cannot_escape_the_hub(hub):
    with pytest.raises(KeyError):
        sm.delete("cache:../../etc")


@pytest.mark.asyncio
async def test_failed_install_reports_error_and_not_installed(hub, monkeypatch):
    def boom(spec):
        raise OSError("offline")

    monkeypatch.setattr(sm, "_download", boom)
    await sm.install(sm.SPEAKERKIT.id)
    row = next(m for m in sm.list_models() if m["id"] == sm.SPEAKERKIT.id)
    assert row["state"] == "failed" and "offline" in row["error"] and not row["installed"]


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_mac_only_models_hidden_elsewhere(hub, monkeypatch, platform):
    from app import osinfo

    monkeypatch.setattr(osinfo, "platform_name", lambda: platform)
    ids = {m["id"] for m in sm.list_models()}
    assert sm.FASTER_WHISPER_LARGE_V3.id in ids
    assert not ids & {sm.WHISPERKIT_TURBO.id, sm.SPEAKERKIT.id, sm.APPLE_SPEECH.id}


def test_mac_only_models_listed_on_macos(hub):
    ids = {m["id"] for m in sm.list_models(apple_installed=False)}
    assert {sm.WHISPERKIT_TURBO.id, sm.SPEAKERKIT.id, sm.APPLE_SPEECH.id} <= ids
