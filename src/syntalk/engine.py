"""Synthesis, effect application and playback. No GTK."""

from __future__ import annotations

import shutil
import subprocess
import threading
import wave
from pathlib import Path
from typing import IO

from .voices import Voice


class EngineError(RuntimeError):
    """Anything the user needs to be told about, phrased for a toast."""


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        raise EngineError(f"{tool} is not installed or not on PATH")
    return path


def _resolve_speaker_id(voice: Voice, speaker_id: int | None) -> int | None:
    """Shared by synthesize() and speak(): validate before anything runs."""
    if voice.is_multi_speaker:
        if speaker_id is None:
            speaker_id = 0
        if not 0 <= speaker_id < voice.num_speakers:
            raise EngineError(
                f"speaker id {speaker_id} out of range "
                f"0..{voice.num_speakers - 1} for {voice.key}"
            )
        return speaker_id
    return None


def _spawn_pipeline(
    sample_rate: int, chain: str | None
) -> tuple[list[subprocess.Popen], IO[bytes]]:
    """Start aplay (and ffmpeg, if an effect chain is set) and return the
    live processes plus the pipe to write raw PCM into. Shared by play()
    and speak() so the two pipelines can never drift apart."""
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

    return procs, sink


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


def _feed_stream(model, text: str, config, sink, playback: "Playback") -> None:
    """Feeder thread body for speak(): pull chunks from the model as they
    are produced and write each one immediately, so playback starts after
    the first chunk instead of the last. Always closes the sink on the way
    out, by any path, so the reader sees EOF and terminates."""
    try:
        for chunk in model.synthesize(text, syn_config=config):
            if playback._cancel.is_set():
                break
            try:
                sink.write(chunk.audio_int16_bytes)
            except (BrokenPipeError, ValueError, OSError):
                break  # reader terminated (Stop); normal path, not an error
    except Exception as exc:  # noqa: BLE001 - surfaced via Playback.error
        playback.error = EngineError(f"synthesis failed: {exc}")
    finally:
        try:
            sink.close()
        except (BrokenPipeError, OSError):
            pass


class Playback:
    """Handle on a running audio pipeline."""

    def __init__(
        self,
        procs: list[subprocess.Popen],
        feeder: threading.Thread | None = None,
    ) -> None:
        self._procs = procs
        self._feeder = feeder
        self._cancel = threading.Event()
        self.error: EngineError | None = None

    def stop(self) -> None:
        # Set the cancel flag FIRST. If the feeder thread is blocked writing
        # into a full pipe, terminating the reader below unblocks it with a
        # BrokenPipeError; the feeder must then see this flag already set so
        # it stops instead of pulling another chunk out of the model.
        self._cancel.set()
        for proc in reversed(self._procs):
            if proc.poll() is None:
                proc.terminate()
        # Bound only the stop path: a wedged ALSA device must not hang the
        # UI forever. Natural completion (wait()) must never impose this
        # deadline -- see _reap().
        self._reap(timeout=10)

    def wait(self) -> None:
        """Block until playback finishes on its own. No deadline: audio
        longer than any fixed timeout must still play to completion."""
        # Join the feeder before reaping so `error` is always settled by
        # the time wait() returns.
        if self._feeder is not None:
            self._feeder.join()
        self._reap()

    def _reap(self, timeout: float | None = None) -> None:
        for proc in self._procs:
            try:
                proc.wait(timeout=timeout)
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

        speaker_id = _resolve_speaker_id(voice, speaker_id)

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

        procs, sink = _spawn_pipeline(sample_rate, chain)
        feeder = threading.Thread(target=_feed, args=(sink, pcm), daemon=True)
        feeder.start()
        return Playback(procs, feeder)

    def speak(
        self,
        voice: Voice,
        text: str,
        *,
        length_scale: float = 1.0,
        speaker_id: int | None = None,
        chain: str | None = None,
    ) -> Playback:
        """Streaming counterpart to synthesize() + play(): validates and
        loads the model first (so a bad speaker id or a failed model load
        still raises EngineError before any audio starts), then spawns the
        playback pipeline immediately and streams synthesis chunks into it
        as they are produced, instead of buffering the whole utterance."""
        if not text.strip():
            return Playback([])

        speaker_id = _resolve_speaker_id(voice, speaker_id)

        from piper import SynthesisConfig

        config = SynthesisConfig(speaker_id=speaker_id, length_scale=length_scale)
        model = self._model(voice)  # raises EngineError before any subprocess exists

        procs, sink = _spawn_pipeline(voice.sample_rate, chain)
        playback = Playback(procs)
        feeder = threading.Thread(
            target=_feed_stream,
            args=(model, text, config, sink, playback),
            daemon=True,
        )
        playback._feeder = feeder
        feeder.start()
        return playback

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
