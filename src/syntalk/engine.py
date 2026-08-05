"""Synthesis, effect application and playback. No GTK."""

from __future__ import annotations

import shutil
import subprocess
import threading
import wave
from pathlib import Path

from .voices import Voice


class EngineError(RuntimeError):
    """Anything the user needs to be told about, phrased for a toast."""


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        raise EngineError(f"{tool} is not installed or not on PATH")
    return path


def _feed(sink, pcm: bytes) -> None:
    try:
        sink.write(pcm)
    except (BrokenPipeError, ValueError, OSError):
        pass  # stopped mid-write; expected
    finally:
        try:
            sink.close()
        except (BrokenPipeError, OSError):
            pass


class Playback:
    """Handle on a running audio pipeline."""

    def __init__(self, procs: list[subprocess.Popen]) -> None:
        self._procs = procs

    def stop(self) -> None:
        for proc in reversed(self._procs):
            if proc.poll() is None:
                proc.terminate()
        self.wait()

    def wait(self) -> None:
        for proc in self._procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class Engine:
    """Loads each voice once, then reuses it."""

    def __init__(self) -> None:
        self._cache: dict[Path, object] = {}

    def _model(self, voice: Voice):
        model = self._cache.get(voice.model_path)
        if model is None:
            from piper import PiperVoice

            try:
                model = PiperVoice.load(str(voice.model_path))
            except Exception as exc:  # noqa: BLE001 - surfaced as a toast
                raise EngineError(f"could not load {voice.key}: {exc}") from exc
            self._cache[voice.model_path] = model
        return model

    def synthesize(
        self,
        voice: Voice,
        text: str,
        *,
        length_scale: float = 1.0,
        speaker_id: int | None = None,
    ) -> bytes:
        if not text.strip():
            return b""

        if voice.is_multi_speaker:
            if speaker_id is None:
                speaker_id = 0
            if not 0 <= speaker_id < voice.num_speakers:
                raise EngineError(
                    f"speaker id {speaker_id} out of range "
                    f"0..{voice.num_speakers - 1} for {voice.key}"
                )
        else:
            speaker_id = None

        from piper import SynthesisConfig

        config = SynthesisConfig(speaker_id=speaker_id, length_scale=length_scale)
        model = self._model(voice)
        try:
            return b"".join(
                chunk.audio_int16_bytes
                for chunk in model.synthesize(text, syn_config=config)
            )
        except EngineError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as a toast
            raise EngineError(f"synthesis failed: {exc}") from exc

    def play(
        self, pcm: bytes, sample_rate: int, *, chain: str | None = None
    ) -> Playback:
        if not pcm:
            return Playback([])

        aplay = _require("aplay")

        if chain:
            ffmpeg = _require("ffmpeg")
            converter = subprocess.Popen(
                [ffmpeg, "-v", "error",
                 "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "-",
                 "-af", chain, "-f", "wav", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
            player = subprocess.Popen([aplay, "-q", "-"], stdin=converter.stdout)
            converter.stdout.close()  # only ffmpeg holds the write end now
            procs = [converter, player]
            sink = converter.stdin
        else:
            player = subprocess.Popen(
                [aplay, "-q", "-r", str(sample_rate),
                 "-f", "S16_LE", "-t", "raw", "-"],
                stdin=subprocess.PIPE,
            )
            procs = [player]
            sink = player.stdin

        threading.Thread(target=_feed, args=(sink, pcm), daemon=True).start()
        return Playback(procs)

    def save_wav(
        self,
        pcm: bytes,
        sample_rate: int,
        path: Path | str,
        *,
        chain: str | None = None,
    ) -> None:
        path = Path(path)
        if chain:
            ffmpeg = _require("ffmpeg")
            result = subprocess.run(
                [ffmpeg, "-v", "error", "-y",
                 "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "-",
                 "-af", chain, str(path)],
                input=pcm,
                capture_output=True,
            )
            if result.returncode != 0:
                message = result.stderr.decode(errors="replace").strip()
                raise EngineError(message or "ffmpeg failed")
        else:
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(sample_rate)
                handle.writeframes(pcm)
