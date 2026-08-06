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


class _Chunk:
    """Stand-in for piper.voice.AudioChunk: only audio_int16_bytes is used."""

    def __init__(self, pcm: bytes) -> None:
        self.audio_int16_bytes = pcm


class _SlowModel:
    """Fake PiperVoice that yields chunks with a per-chunk delay, so tests
    can exercise streaming timing without a real model or GPU/CPU inference
    cost. Injected straight into Engine._cache, bypassing PiperVoice.load."""

    def __init__(self, chunk_count: int, chunk_delay: float) -> None:
        self.chunk_count = chunk_count
        self.chunk_delay = chunk_delay

    def synthesize(self, text, syn_config=None):
        for _ in range(self.chunk_count):
            time.sleep(self.chunk_delay)
            yield _Chunk(b"\x00\x00" * 512)


class _FailingModel:
    """Fake model that yields one good chunk, then blows up mid-stream."""

    def synthesize(self, text, syn_config=None):
        yield _Chunk(b"\x00\x00" * 512)
        raise RuntimeError("boom")


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


# --------------------------------------------------------------- speak()


def test_speak_blank_text_spawns_no_processes(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no subprocess should be spawned for blank text")

    monkeypatch.setattr("syntalk.engine.subprocess.Popen", explode)

    playback = Engine().speak(_voice(), "   \n\t ")
    playback.wait()

    assert playback._procs == []


def test_speak_speaker_id_out_of_range_raises_before_spawning(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no subprocess should be spawned for a bad speaker id")

    monkeypatch.setattr("syntalk.engine.subprocess.Popen", explode)

    with pytest.raises(EngineError, match="out of range"):
        Engine().speak(_voice(num_speakers=4), "hello", speaker_id=9)


def test_speak_returns_long_before_synthesis_completes():
    """The point of streaming: speak() must not wait for the last chunk.
    Prove it by timing synthesize() (fully buffered) against speak() (which
    only has to spawn the pipeline and start a feeder thread) for the same
    slow, multi-chunk synthesis."""
    if shutil.which("aplay") is None:
        pytest.skip("aplay not installed")

    voice = _voice()
    text = "word " * 400  # ~400 words: representative long-form input

    synth_engine = Engine()
    synth_engine._cache[voice.model_path] = _SlowModel(chunk_count=15, chunk_delay=0.1)
    started = time.monotonic()
    pcm = synth_engine.synthesize(voice, text)
    synth_elapsed = time.monotonic() - started
    assert pcm  # sanity: the fake model really produced audio

    speak_engine = Engine()
    speak_engine._cache[voice.model_path] = _SlowModel(chunk_count=15, chunk_delay=0.1)
    started = time.monotonic()
    playback = speak_engine.speak(voice, text)
    speak_elapsed = time.monotonic() - started
    playback.stop()

    assert speak_elapsed < synth_elapsed / 3, (
        f"speak() took {speak_elapsed:.2f}s, synthesize() took "
        f"{synth_elapsed:.2f}s for the same text -- streaming did not help"
    )
    assert speak_elapsed < 0.5


def test_stop_cancels_synthesis_before_completion():
    """Second half of the streaming win: Stop must interrupt synthesis, not
    just playback. Start a speak() that would take ~10s if left alone, stop
    it almost immediately, and require both a prompt return and dead
    processes."""
    if shutil.which("aplay") is None:
        pytest.skip("aplay not installed")

    voice = _voice()
    engine = Engine()
    engine._cache[voice.model_path] = _SlowModel(chunk_count=50, chunk_delay=0.2)

    playback = engine.speak(voice, "word " * 400)
    time.sleep(0.3)

    started = time.monotonic()
    playback.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"stop() took {elapsed:.1f}s to return"
    for proc in playback._procs:
        assert proc.poll() is not None, "process still alive after stop()"


def test_midstream_synthesis_failure_is_recorded_on_playback():
    if shutil.which("aplay") is None:
        pytest.skip("aplay not installed")

    voice = _voice()
    engine = Engine()
    engine._cache[voice.model_path] = _FailingModel()

    playback = engine.speak(voice, "hello")
    playback.wait()

    assert isinstance(playback.error, EngineError)
    assert "boom" in str(playback.error)
