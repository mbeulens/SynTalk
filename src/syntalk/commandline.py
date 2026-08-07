"""Reconstruct the shell command equivalent to a play or save action.

Pure stdlib, no GTK, no subprocess execution -- this module only builds
strings. It mirrors `reference/say` and `reference/sayfx`, which is where
this project's synthesis pipeline came from: piper's `--output-raw` piped
straight into `aplay` when there is no effect, or through an `ffmpeg -af`
stage when there is. That is also exactly what `Engine.play` / `save_wav`
do under the hood, so the string returned here is genuinely what a user
could type by hand in a terminal to reproduce what SynTalk just did.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from .voices import Voice


def _piper_executable() -> str:
    """The `piper` console script, as a token the user can actually run.

    A bare `piper` is almost never on PATH: it is installed into the same
    venv as SynTalk itself, so emitting the bare name produced a command
    that failed with "Command 'piper' not found" for every venv install --
    and Ubuntu unhelpfully suggests `apt install piper`, which is an
    unrelated gaming-mouse configuration tool. Resolve it next to the
    running interpreter, the same way the empty-state download hint does.
    Fall back to the bare name for system-wide installs where PATH is right.
    """
    candidate = Path(sys.executable).parent / "piper"
    return shlex.quote(str(candidate)) if candidate.exists() else "piper"


def _piper_invocation(
    voice: Voice, length_scale: float, speaker_id: int | None
) -> list[str]:
    tokens = [
        _piper_executable(),
        "-m", shlex.quote(str(voice.model_path)),
        "--length-scale", str(length_scale),
    ]
    if speaker_id is not None and voice.is_multi_speaker:
        tokens += ["-s", str(speaker_id)]
    return tokens


def play_command(
    voice: Voice,
    text: str,
    *,
    length_scale: float = 1.0,
    speaker_id: int | None = None,
    chain: str | None = None,
) -> str:
    """The shell command that reproduces a play SynTalk just did."""
    tokens = [
        "printf", "%s", shlex.quote(text), "|",
        *_piper_invocation(voice, length_scale, speaker_id),
        "--output-raw",
    ]
    if chain:
        tokens += [
            "|", "ffmpeg", "-v", "error",
            "-f", "s16le", "-ar", str(voice.sample_rate), "-ac", "1", "-i", "-",
            "-af", shlex.quote(chain), "-f", "wav", "-",
            "|", "aplay", "-q", "-",
        ]
    else:
        tokens += [
            "|", "aplay", "-q",
            "-r", str(voice.sample_rate), "-f", "S16_LE", "-t", "raw", "-",
        ]
    return " ".join(tokens)


def save_command(
    voice: Voice,
    text: str,
    path,
    *,
    length_scale: float = 1.0,
    speaker_id: int | None = None,
    chain: str | None = None,
) -> str:
    """The shell command that reproduces a save SynTalk just did."""
    quoted_path = shlex.quote(str(path))
    tokens = [
        "printf", "%s", shlex.quote(text), "|",
        *_piper_invocation(voice, length_scale, speaker_id),
    ]
    if chain:
        tokens += [
            "--output-raw",
            "|", "ffmpeg", "-v", "error", "-y",
            "-f", "s16le", "-ar", str(voice.sample_rate), "-ac", "1", "-i", "-",
            "-af", shlex.quote(chain), quoted_path,
        ]
    else:
        tokens += ["-f", quoted_path]
    return " ".join(tokens)
