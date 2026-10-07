"""WAV slice reading + NumPy resampling (scipy is not in the default bundle)."""
import wave

import numpy as np

from app.audio.wav import load_wav_16k, resample_to_16k, wav_duration_s


def _wav(path, sr, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.asarray(samples, dtype=np.int16).tobytes())


def test_slice_length_and_position(tmp_path):
    sr = 48000
    t = np.arange(sr * 10) / sr
    ramp = (t * 1000).astype(np.int16)  # value encodes the time
    _wav(tmp_path / "a.wav", sr, ramp)
    assert wav_duration_s(str(tmp_path / "a.wav")) == 10.0
    x = load_wav_16k(str(tmp_path / "a.wav"), 2.0, 5.0)
    assert x.size == 16000 * 3
    mid = x[x.size // 2] * 32768 / 1000  # ~3.5 s
    assert abs(mid - 3.5) < 0.05


def test_decimation_keeps_speech_band_and_removes_aliasing():
    sr = 48000
    t = np.arange(sr) / sr
    tone = np.sin(2 * np.pi * 1000 * t)  # in band
    high = np.sin(2 * np.pi * 15000 * t)  # above 8 kHz: must not alias into the output
    out_tone = resample_to_16k(tone.astype(np.float32), sr)
    out_high = resample_to_16k(high.astype(np.float32), sr)
    assert out_tone.size == 16000
    assert 0.6 < np.sqrt(np.mean(out_tone[100:-100] ** 2)) < 0.75  # ~0.707 RMS preserved
    assert np.sqrt(np.mean(out_high[100:-100] ** 2)) < 0.05


def test_non_integer_rate_falls_back_to_interpolation():
    out = resample_to_16k(np.zeros(44100, dtype=np.float32), 44100)
    assert out.size == 16000
