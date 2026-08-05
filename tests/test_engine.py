import shutil
import time
import wave
from pathlib import Path

import pytest

from syntalk.engine import Engine, EngineError
from syntalk.voices import Voice

SILENCE = b"\x00\x00" * 2205  # 0.1 s of 22050 Hz mono s16le


def _voice(num_speakers=1):
    return Voice(
        model_path=Path("/nonexistent/fake.onnx"),
        key="fake-voice",
        display_name="Fake",
        language_code="en_US",
        language_label="English (United States)",
        sample_rate=22050,
        num_speakers=num_speakers,
        speaker_names=tuple(f"s{i}" for i in range(num_speakers)),
    )


def test_blank_text_synthesizes_nothing():
    assert Engine().synthesize(_voice(), "   \n\t ") == b""


def test_speaker_id_out_of_range_raises():
    engine = Engine()

    with pytest.raises(EngineError, match="out of range"):
        engine.synthesize(_voice(num_speakers=4), "hello", speaker_id=9)


def test_negative_speaker_id_raises():
    with pytest.raises(EngineError, match="out of range"):
        Engine().synthesize(_voice(num_speakers=4), "hello", speaker_id=-1)


def test_playing_empty_pcm_spawns_no_processes(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no subprocess should be spawned for empty audio")

    monkeypatch.setattr("syntalk.engine.subprocess.Popen", explode)

    playback = Engine().play(b"", 22050)
    playback.wait()

    assert playback._procs == []


def test_save_wav_without_effect_writes_valid_file(tmp_path):
    out = tmp_path / "out.wav"

    Engine().save_wav(SILENCE, 22050, out)

    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 22050
        assert wf.getnframes() == 2205


def test_missing_tool_raises_engine_error(monkeypatch, tmp_path):
    monkeypatch.setattr("syntalk.engine.shutil.which", lambda _: None)

    with pytest.raises(EngineError, match="ffmpeg"):
        Engine().save_wav(SILENCE, 22050, tmp_path / "x.wav", chain="volume=1.0")


def test_wait_blocks_for_the_full_duration_of_long_playback():
    """Regression for the bug that SIGKILLed every utterance past 10s:
    Playback.wait() must not impose the 10s deadline that belongs only to
    stop(). 15s of silence must play to natural completion, returning well
    past 10s with returncode 0 -- not killed at the old fixed timeout."""
    if shutil.which("aplay") is None:
        pytest.skip("aplay not installed")

    seconds = 15
    rate = 22050
    pcm = b"\x00\x00" * rate * seconds

    playback = Engine().play(pcm, rate)
    started = time.monotonic()
    playback.wait()
    elapsed = time.monotonic() - started

    assert elapsed > 14, f"wait() returned after only {elapsed:.1f}s"
    assert playback._procs[0].returncode == 0
