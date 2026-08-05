"""Discovery of installed Piper voice models. No GTK, no piper import."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICES_DIR = Path.home() / ".local" / "share" / "piper-voices"

# Keys whose middle segment should not be naively title-cased.
_NAME_OVERRIDES = {
    "vctk": "VCTK",
    "l2arctic": "L2Arctic",
}


@dataclass(frozen=True)
class Voice:
    model_path: Path
    key: str
    display_name: str
    language_code: str
    language_label: str
    sample_rate: int
    num_speakers: int
    speaker_names: tuple[str, ...]

    @property
    def is_multi_speaker(self) -> bool:
        return self.num_speakers > 1


def _display_name(key: str) -> str:
    """'en_GB-northern_english_male-medium' -> 'Northern English Male'."""
    parts = key.split("-")
    middle = "-".join(parts[1:-1]) if len(parts) >= 3 else key
    if middle in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[middle]
    return middle.replace("_", " ").title()


def _language_label(language: dict) -> str:
    name = language.get("name_english")
    country = language.get("country_english")
    if name and country:
        return f"{name} ({country})"
    return language.get("code", "Unknown")


def _load_voice(model_path: Path) -> Voice | None:
    config_path = model_path.with_name(model_path.name + ".json")
    try:
        meta = json.loads(config_path.read_text())
        sample_rate = int(meta["audio"]["sample_rate"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"syntalk: skipping {model_path.name}: {exc}", file=sys.stderr)
        return None

    id_map = meta.get("speaker_id_map") or {}
    speaker_names = tuple(
        name for name, _ in sorted(id_map.items(), key=lambda kv: kv[1])
    )
    language = meta.get("language") or {}
    key = model_path.stem

    return Voice(
        model_path=model_path,
        key=key,
        display_name=_display_name(key),
        language_code=language.get("code", "unknown"),
        language_label=_language_label(language),
        sample_rate=sample_rate,
        num_speakers=int(meta.get("num_speakers", 1)),
        speaker_names=speaker_names,
    )


def discover(voices_dir: Path = DEFAULT_VOICES_DIR) -> list[Voice]:
    """Every usable voice in *voices_dir*, sorted by language then name."""
    voices_dir = Path(voices_dir)
    if not voices_dir.is_dir():
        return []
    voices = [
        voice
        for path in sorted(voices_dir.glob("*.onnx"))
        if (voice := _load_voice(path)) is not None
    ]
    voices.sort(key=lambda v: (v.language_label, v.display_name))
    return voices


def find(key: str, voices: list[Voice]) -> Voice | None:
    return next((v for v in voices if v.key == key), None)
