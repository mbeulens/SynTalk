# SynTalk GTK 4 GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GTK 4 desktop app that lists the installed Piper voices in a sidebar, takes typed text in a large field, and speaks it — with character effects and a GNOME launcher icon.

**Architecture:** Three GTK-free core modules (`voices`, `effects`, `engine`) do discovery, preset handling and audio. A single `gui` module is the only thing that imports `gi`. This boundary keeps the CLI from `HANDOFF.md` a thin later addition rather than a rewrite.

**Tech Stack:** Python 3.12, PyGObject (system `python3-gi`, GTK 4.14), libadwaita 1, piper-tts 1.6.x, ffmpeg, aplay, uv, pytest.

**Spec:** `docs/superpowers/specs/2026-08-05-syntalk-gtk-gui-design.md`

## Global Constraints

- **Python:** `requires-python = ">=3.12"`. Target machine has 3.12.3.
- **Piper pin:** `piper-tts>=1.6,<2`. API verified against 1.6.0.
- **PyGObject is NOT a pip dependency.** It comes from the system. The venv MUST be created with `uv venv --system-site-packages` or `import gi` fails.
- **Voices directory:** `~/.local/share/piper-voices`. Never hardcode a voice list.
- **Sample rate always comes from the voice's `.json`** (`meta["audio"]["sample_rate"]`). Never hardcode 22050.
- **App ID:** `nl.syntec.SynTalk` — used for the GTK application id, the `.desktop` filename, and the icon filename. All three must match exactly.
- **No network calls at runtime.** Everything is offline after model download.
- **Only `src/syntalk/gui.py` may `import gi`.** Any other module importing GTK is a defect.
- **`reference/say` and `reference/sayfx` are read-only.** Never edit them.
- **Git workflow:** all work on `dev`. Every commit bumps the patch version in **both** `VERSION` and the `**Version:**` line of `README.md`, then pushes to `dev`. Versions containing 13 as a component (`0.1.13`, `0.13.x`, `13.x`) are skipped with the commit description `To be sure to be sure!`.
- **Commit trailer:** every commit ends with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, `syntalk` entry point, piper pin, pytest dev group |
| `src/syntalk/__init__.py` | Version constant only |
| `src/syntalk/voices.py` | `Voice` dataclass, `discover()`, `find()`. No GTK, no piper import. |
| `src/syntalk/effects.py` | `Effect` dataclass, `EFFECTS` dict, `filter_chain()`, `apply_text_rewrite()`. Pure string work. |
| `src/syntalk/engine.py` | `Engine` (model cache, synthesize, play, save_wav), `Playback`, `EngineError` |
| `src/syntalk/gui.py` | `SynTalkWindow`, `SynTalkApp`. The only `gi` importer. |
| `src/syntalk/__main__.py` | `main()` entry point |
| `tests/conftest.py` | `voices_dir` and `write_voice` fixtures |
| `tests/test_voices.py` | Discovery, metadata parsing, naming, sorting, malformed handling |
| `tests/test_effects.py` | `@SR@` substitution, atempo splitting, yoda rewrite, preset integrity |
| `data/nl.syntec.SynTalk.desktop` | Launcher entry |
| `data/icons/hicolor/scalable/apps/nl.syntec.SynTalk.svg` | App icon |
| `install.sh` / `uninstall.sh` | Venv setup + desktop integration |

---

### Task 1: Project scaffold and voice discovery

**Files:**
- Create: `pyproject.toml`
- Create: `src/syntalk/__init__.py`
- Create: `src/syntalk/voices.py`
- Create: `tests/conftest.py`
- Create: `tests/test_voices.py`
- Modify: `VERSION`, `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `syntalk.voices.Voice` — frozen dataclass with fields `model_path: Path`, `key: str`, `display_name: str`, `language_code: str`, `language_label: str`, `sample_rate: int`, `num_speakers: int`, `speaker_names: tuple[str, ...]`, and property `is_multi_speaker -> bool`.
  - `syntalk.voices.discover(voices_dir: Path = DEFAULT_VOICES_DIR) -> list[Voice]`
  - `syntalk.voices.find(key: str, voices: list[Voice]) -> Voice | None`
  - `syntalk.voices.DEFAULT_VOICES_DIR: Path`

- [ ] **Step 1: Create the package scaffold**

Create `pyproject.toml`:

```toml
[project]
name = "syntalk"
version = "0.1.3"
description = "Local neural text-to-speech with a GTK 4 interface"
requires-python = ">=3.12"
dependencies = ["piper-tts>=1.6,<2"]

# NOTE: PyGObject is deliberately absent. It is provided by the system
# (python3-gi) and the venv must be created with --system-site-packages.

[project.scripts]
syntalk = "syntalk.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/syntalk"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `src/syntalk/__init__.py`:

```python
"""SynTalk — local neural text-to-speech."""

__version__ = "0.1.3"
```

- [ ] **Step 2: Create the venv and install**

```bash
cd /home/beuner/Development/Local/SynTalk
uv venv --system-site-packages
uv pip install -e . --group dev
.venv/bin/python -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk; print('gi ok')"
.venv/bin/python -c "from piper import PiperVoice; print('piper ok')"
```

Expected: both print `ok`. If `gi ok` fails, the venv was created without `--system-site-packages` — delete `.venv` and redo.

Add `.venv/` to `.gitignore`.

- [ ] **Step 3: Write the test fixtures**

Create `tests/conftest.py`:

```python
import json

import pytest


def _meta(
    sample_rate=22050,
    num_speakers=1,
    speaker_id_map=None,
    code="en_US",
    name_english="English",
    country_english="United States",
):
    family, _, region = code.partition("_")
    return {
        "audio": {"sample_rate": sample_rate, "quality": "high"},
        "num_speakers": num_speakers,
        "speaker_id_map": speaker_id_map or {},
        "language": {
            "code": code,
            "family": family,
            "region": region,
            "name_native": name_english,
            "name_english": name_english,
            "country_english": country_english,
        },
    }


@pytest.fixture
def voices_dir(tmp_path):
    d = tmp_path / "piper-voices"
    d.mkdir()
    return d


@pytest.fixture
def write_voice():
    """Write a stub .onnx plus a realistic .onnx.json sidecar."""

    def _write(directory, key, **kwargs):
        (directory / f"{key}.onnx").write_bytes(b"")
        (directory / f"{key}.onnx.json").write_text(json.dumps(_meta(**kwargs)))

    return _write
```

- [ ] **Step 4: Write the failing tests**

Create `tests/test_voices.py`:

```python
import json

from syntalk.voices import discover, find


def test_discovers_each_installed_model(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")
    write_voice(voices_dir, "nl_NL-pim-medium", code="nl_NL",
                name_english="Dutch", country_english="Netherlands")

    voices = discover(voices_dir)

    # Sorted by language label: "Dutch (Netherlands)" < "English (United States)".
    assert [v.key for v in voices] == ["nl_NL-pim-medium", "en_US-lessac-high"]


def test_parses_metadata(voices_dir, write_voice):
    write_voice(voices_dir, "en_GB-vctk-medium", sample_rate=16000,
                num_speakers=3, speaker_id_map={"p239": 0, "p236": 1, "p264": 2},
                code="en_GB", name_english="English",
                country_english="Great Britain")

    voice = discover(voices_dir)[0]

    assert voice.sample_rate == 16000
    assert voice.num_speakers == 3
    assert voice.is_multi_speaker is True
    assert voice.speaker_names == ("p239", "p236", "p264")
    assert voice.language_code == "en_GB"
    assert voice.language_label == "English (Great Britain)"


def test_single_speaker_voice_is_not_multi_speaker(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")

    voice = discover(voices_dir)[0]

    assert voice.num_speakers == 1
    assert voice.is_multi_speaker is False
    assert voice.speaker_names == ()


def test_display_name_derivation(voices_dir, write_voice):
    for key in [
        "en_US-lessac-high",
        "en_GB-northern_english_male-medium",
        "en_GB-vctk-medium",
        "en_US-l2arctic-medium",
    ]:
        write_voice(voices_dir, key)

    names = {v.key: v.display_name for v in discover(voices_dir)}

    assert names["en_US-lessac-high"] == "Lessac"
    assert names["en_GB-northern_english_male-medium"] == "Northern English Male"
    assert names["en_GB-vctk-medium"] == "VCTK"
    assert names["en_US-l2arctic-medium"] == "L2Arctic"


def test_malformed_sidecar_is_skipped_not_fatal(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")
    (voices_dir / "broken-medium.onnx").write_bytes(b"")
    (voices_dir / "broken-medium.onnx.json").write_text("{ not json")

    voices = discover(voices_dir)

    assert [v.key for v in voices] == ["en_US-lessac-high"]


def test_missing_sidecar_is_skipped(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")
    (voices_dir / "orphan-medium.onnx").write_bytes(b"")

    assert [v.key for v in discover(voices_dir)] == ["en_US-lessac-high"]


def test_sorted_by_language_then_name(voices_dir, write_voice):
    write_voice(voices_dir, "nl_NL-pim-medium", code="nl_NL",
                name_english="Dutch", country_english="Netherlands")
    write_voice(voices_dir, "en_US-lessac-high")
    write_voice(voices_dir, "en_GB-alan-medium", code="en_GB",
                name_english="English", country_english="Great Britain")

    labels = [(v.language_label, v.display_name) for v in discover(voices_dir)]

    assert labels == [
        ("Dutch (Netherlands)", "Pim"),
        ("English (Great Britain)", "Alan"),
        ("English (United States)", "Lessac"),
    ]


def test_missing_directory_returns_empty(tmp_path):
    assert discover(tmp_path / "nope") == []


def test_find_hit_and_miss(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")
    voices = discover(voices_dir)

    assert find("en_US-lessac-high", voices).key == "en_US-lessac-high"
    assert find("does-not-exist", voices) is None


def test_language_label_falls_back_to_code(voices_dir, write_voice):
    write_voice(voices_dir, "xx_YY-mystery-medium")
    path = voices_dir / "xx_YY-mystery-medium.onnx.json"
    meta = json.loads(path.read_text())
    meta["language"] = {"code": "xx_YY"}
    path.write_text(json.dumps(meta))

    assert discover(voices_dir)[0].language_label == "xx_YY"
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_voices.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'syntalk.voices'`

- [ ] **Step 6: Implement `voices.py`**

Create `src/syntalk/voices.py`:

```python
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_voices.py -v`
Expected: PASS, 10 tests.

- [ ] **Step 8: Verify against the real voices directory**

Run:

```bash
.venv/bin/python -c "
from syntalk.voices import discover
for v in discover():
    print(f'{v.key:38} {v.display_name:22} {v.language_label:26} spk={v.num_speakers}')
"
```

Expected: all 8 installed voices, `VCTK` showing `spk=109` and `L2Arctic` `spk=24`.

- [ ] **Step 9: Commit**

```bash
printf '0.1.3\n' > VERSION
sed -i 's/^\*\*Version:\*\* .*/**Version:** 0.1.3/' README.md
git add -A
git commit -m "$(cat <<'EOF'
feat: voice discovery and project scaffold v0.1.3

Voice dataclass plus discover()/find() reading the .onnx.json sidecars.
Language labels derived from voice metadata, no hardcoded map.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin dev
```

---

### Task 2: Effect presets

**Files:**
- Create: `src/syntalk/effects.py`
- Create: `tests/test_effects.py`
- Modify: `VERSION`, `README.md`

**Interfaces:**
- Consumes: `syntalk.voices.discover` (only in the preset-integrity test).
- Produces:
  - `syntalk.effects.Effect` — frozen dataclass with `name: str`, `voice_key: str`, `length_scale: float`, `chain: str`, `rewrites_text: bool = False`.
  - `syntalk.effects.EFFECTS: dict[str, Effect]` — the ten presets, keyed by name.
  - `syntalk.effects.filter_chain(effect: Effect, sample_rate: int) -> str`
  - `syntalk.effects.apply_text_rewrite(effect: Effect, text: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_effects.py`:

```python
import pytest

from syntalk.effects import EFFECTS, apply_text_rewrite, filter_chain
from syntalk.voices import discover


def test_all_ten_presets_present():
    assert set(EFFECTS) == {
        "yoda", "robot", "chipmunk", "demon", "giant",
        "ghost", "radio", "drunk", "announcer", "tiny",
    }


def test_sample_rate_substituted():
    chain = filter_chain(EFFECTS["demon"], 16000)

    assert "@SR@" not in chain
    assert "asetrate=16000*0.62" in chain
    assert "aresample=16000" in chain


def test_chain_without_sample_rate_placeholder_is_untouched():
    chain = filter_chain(EFFECTS["radio"], 22050)

    assert chain == EFFECTS["radio"].chain


def test_existing_presets_keep_their_atempo_values():
    # Every shipped preset is already inside ffmpeg's 0.5-2.0 window.
    for effect in EFFECTS.values():
        chain = filter_chain(effect, 22050)
        for part in chain.split(","):
            if part.startswith("atempo="):
                assert 0.5 <= float(part.split("=")[1]) <= 2.0


@pytest.mark.parametrize("value", [3.0, 5.0, 0.3, 0.2, 8.0])
def test_out_of_range_atempo_is_split_into_valid_factors(value):
    from syntalk.effects import Effect

    effect = Effect(name="t", voice_key="x", length_scale=1.0,
                    chain=f"atempo={value}")

    parts = filter_chain(effect, 22050).split(",")
    factors = [float(p.split("=")[1]) for p in parts]

    assert all(0.5 <= f <= 2.0 for f in factors)
    product = 1.0
    for f in factors:
        product *= f
    assert product == pytest.approx(value)


def test_atempo_split_leaves_other_filters_alone():
    from syntalk.effects import Effect

    effect = Effect(name="t", voice_key="x", length_scale=1.0,
                    chain="asetrate=@SR@*4.0,aresample=@SR@,atempo=4.0,volume=1.2")

    chain = filter_chain(effect, 22050)

    assert chain.startswith("asetrate=22050*4.0,aresample=22050,")
    assert chain.endswith(",volume=1.2")
    assert chain.count("atempo=") == 2


def test_yoda_rewrites_word_order():
    result = apply_text_rewrite(EFFECTS["yoda"], "you must learn patience young one")

    assert result == "patience young one, you must learn, yes"


def test_yoda_handles_multiple_sentences():
    result = apply_text_rewrite(EFFECTS["yoda"],
                               "you must learn patience. much to learn you still have")

    assert result == (
        "learn patience, you must, yes. "
        "you still have, much to learn, yes"
    )


def test_yoda_leaves_short_clauses_alone():
    assert apply_text_rewrite(EFFECTS["yoda"], "do or do") == "do or do"


def test_non_rewriting_effects_pass_text_through():
    text = "resistance is futile you will be assimilated"

    assert apply_text_rewrite(EFFECTS["robot"], text) == text


def test_only_yoda_rewrites():
    rewriters = [e.name for e in EFFECTS.values() if e.rewrites_text]

    assert rewriters == ["yoda"]


def test_every_preset_names_an_installed_voice():
    installed = {v.key for v in discover()}
    if not installed:
        pytest.skip("no voices installed on this machine")

    for effect in EFFECTS.values():
        assert effect.voice_key in installed, (
            f"preset {effect.name} wants missing voice {effect.voice_key}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_effects.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'syntalk.effects'`

- [ ] **Step 3: Implement `effects.py`**

Create `src/syntalk/effects.py`. The ten chains are transcribed verbatim from
`reference/sayfx` lines 19-28 — do not retune them.

```python
"""Character effect presets. Pure string manipulation, no GTK, no audio."""

from __future__ import annotations

import re
from dataclasses import dataclass

# ffmpeg refuses an atempo outside this window in a single filter instance.
_ATEMPO_MIN = 0.5
_ATEMPO_MAX = 2.0

_ATEMPO_RE = re.compile(r"atempo=([0-9]*\.?[0-9]+)")


@dataclass(frozen=True)
class Effect:
    name: str
    voice_key: str
    length_scale: float
    chain: str
    rewrites_text: bool = False


_PRESETS = [
    Effect(
        "yoda", "en_GB-alan-medium", 1.45,
        "asetrate=@SR@*1.22,aresample=@SR@,atempo=0.82,"
        "vibrato=f=6:d=0.35,aecho=0.8:0.7:22:0.18",
        rewrites_text=True,
    ),
    Effect(
        "robot", "en_US-lessac-high", 1.0,
        "asetrate=@SR@*0.92,aresample=@SR@,atempo=1.09,"
        "flanger=delay=6:depth=4:speed=1.2,aecho=0.9:0.85:12:0.5,acompressor",
    ),
    Effect(
        "chipmunk", "en_US-lessac-high", 0.92,
        "asetrate=@SR@*1.55,aresample=@SR@,atempo=0.68",
    ),
    Effect(
        "demon", "en_US-lessac-high", 1.25,
        "asetrate=@SR@*0.62,aresample=@SR@,atempo=1.55,"
        "aecho=0.9:0.9:180:0.4,acompressor",
    ),
    Effect(
        "giant", "en_GB-alan-medium", 1.35,
        "asetrate=@SR@*0.74,aresample=@SR@,atempo=1.3,aecho=0.9:0.88:320:0.45",
    ),
    Effect(
        "ghost", "en_GB-cori-high", 1.3,
        "asetrate=@SR@*0.96,aresample=@SR@,atempo=1.04,"
        "chorus=0.6:0.9:55:0.4:0.25:2,aecho=0.9:0.9:480:0.6,highpass=f=180",
    ),
    Effect(
        "radio", "en_US-lessac-high", 1.0,
        "highpass=f=500,lowpass=f=2600,acrusher=bits=10:mode=log,volume=1.4",
    ),
    Effect(
        "drunk", "en_US-lessac-high", 1.32,
        "vibrato=f=2.4:d=0.7,atempo=0.95,aecho=0.7:0.6:60:0.2",
    ),
    Effect(
        "announcer", "en_US-lessac-high", 1.08,
        "asetrate=@SR@*0.9,aresample=@SR@,atempo=1.11,"
        "aecho=0.85:0.75:240:0.3,acompressor,volume=1.3",
    ),
    Effect(
        "tiny", "en_GB-cori-high", 0.95,
        "asetrate=@SR@*1.32,aresample=@SR@,atempo=0.8,highpass=f=400",
    ),
]

EFFECTS: dict[str, Effect] = {e.name: e for e in _PRESETS}


def _atempo_factors(value: float) -> list[float]:
    """Factors inside ffmpeg's window whose product is *value*."""
    if value <= 0:
        raise ValueError(f"atempo must be positive, got {value}")
    factors: list[float] = []
    remaining = value
    while remaining > _ATEMPO_MAX:
        factors.append(_ATEMPO_MAX)
        remaining /= _ATEMPO_MAX
    while remaining < _ATEMPO_MIN:
        factors.append(_ATEMPO_MIN)
        remaining /= _ATEMPO_MIN
    factors.append(remaining)
    return factors


def _split_atempo(chain: str) -> str:
    def replace(match: re.Match[str]) -> str:
        factors = _atempo_factors(float(match.group(1)))
        if len(factors) == 1:
            return match.group(0)
        return ",".join(f"atempo={f:g}" for f in factors)

    return _ATEMPO_RE.sub(replace, chain)


def filter_chain(effect: Effect, sample_rate: int) -> str:
    """The preset's ffmpeg chain, ready to hand to -af."""
    return _split_atempo(effect.chain.replace("@SR@", str(sample_rate)))


def _yodafy(clause: str) -> str:
    words = clause.split()
    if len(words) < 4:
        return clause
    half = len(words) // 2
    return f"{' '.join(words[half:])}, {' '.join(words[:half])}, yes"


def apply_text_rewrite(effect: Effect, text: str) -> str:
    """Yoda word order. Every other preset returns *text* unchanged."""
    if not effect.rewrites_text:
        return text
    clauses = [c.strip() for c in re.split(r"[.!?]+", text) if c.strip()]
    return ". ".join(_yodafy(c) for c in clauses)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_effects.py -v`
Expected: PASS, 16 tests (5 of them parametrized).

- [ ] **Step 5: Cross-check a chain against the bash prototype**

Run:

```bash
.venv/bin/python -c "
from syntalk.effects import EFFECTS, filter_chain
print(filter_chain(EFFECTS['ghost'], 22050))
"
grep -o 'en_GB-cori-high|1.3|.*' reference/sayfx | head -1
```

Expected: the printed chain matches the portion after the second `|` in the grep
output, with `@SR@` replaced by `22050`.

- [ ] **Step 6: Commit**

```bash
printf '0.1.4\n' > VERSION
sed -i 's/^\*\*Version:\*\* .*/**Version:** 0.1.4/' README.md
git add -A
git commit -m "$(cat <<'EOF'
feat: character effect presets v0.1.4

Ten presets transcribed from reference/sayfx, with @SR@ substitution,
atempo range splitting, and the yoda word-order rewrite.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin dev
```

---

### Task 3: Synthesis and playback engine

**Files:**
- Create: `src/syntalk/engine.py`
- Create: `tests/test_engine.py`
- Modify: `VERSION`, `README.md`

**Interfaces:**
- Consumes: `syntalk.voices.Voice`.
- Produces:
  - `syntalk.engine.EngineError` — `RuntimeError` subclass.
  - `syntalk.engine.Playback` — has `.stop() -> None` and `.wait() -> None`.
  - `syntalk.engine.Engine` with:
    - `synthesize(voice: Voice, text: str, *, length_scale: float = 1.0, speaker_id: int | None = None) -> bytes`
    - `play(pcm: bytes, sample_rate: int, *, chain: str | None = None) -> Playback`
    - `save_wav(pcm: bytes, sample_rate: int, path: Path | str, *, chain: str | None = None) -> None`

- [ ] **Step 1: Write the failing tests**

Playback needs a sound card, so the automated tests cover the logic that does not:
speaker-id validation, empty-input short-circuit, missing-tool errors, and plain
WAV writing.

Create `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'syntalk.engine'`

- [ ] **Step 3: Implement `engine.py`**

Create `src/syntalk/engine.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_engine.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Hear it — manual end-to-end check**

Run:

```bash
.venv/bin/python -c "
from syntalk.engine import Engine
from syntalk.effects import EFFECTS, filter_chain, apply_text_rewrite
from syntalk.voices import discover, find

voices = discover()
engine = Engine()

lessac = find('en_US-lessac-high', voices)
pcm = engine.synthesize(lessac, 'SynTalk core is working.')
engine.play(pcm, lessac.sample_rate).wait()

demon = EFFECTS['demon']
voice = find(demon.voice_key, voices)
pcm = engine.synthesize(voice, apply_text_rewrite(demon, 'Your soul is mine.'),
                        length_scale=demon.length_scale)
engine.play(pcm, voice.sample_rate,
            chain=filter_chain(demon, voice.sample_rate)).wait()

vctk = find('en_GB-vctk-medium', voices)
pcm = engine.synthesize(vctk, 'Speaker forty two reporting.', speaker_id=42)
engine.play(pcm, vctk.sample_rate).wait()
"
```

Expected: three utterances — plain, demon-processed, and VCTK speaker 42.
Confirm all three are audible before continuing.

- [ ] **Step 6: Commit**

```bash
printf '0.1.5\n' > VERSION
sed -i 's/^\*\*Version:\*\* .*/**Version:** 0.1.5/' README.md
git add -A
git commit -m "$(cat <<'EOF'
feat: synthesis and playback engine v0.1.5

Model cache, PCM synthesis, ffmpeg effect pass over a stdin pipe rather
than temp files, stoppable playback handle, WAV export.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin dev
```

---

### Task 4: The GTK 4 interface

**Files:**
- Create: `src/syntalk/gui.py`
- Create: `src/syntalk/__main__.py`
- Modify: `VERSION`, `README.md`

**Interfaces:**
- Consumes: `syntalk.voices.discover/find/Voice`, `syntalk.effects.EFFECTS/filter_chain/apply_text_rewrite`, `syntalk.engine.Engine/EngineError/Playback`.
- Produces: `syntalk.gui.SynTalkApp`, `syntalk.gui.APP_ID`, `syntalk.__main__.main() -> int`.

- [ ] **Step 1: Implement `gui.py`**

Create `src/syntalk/gui.py`:

```python
"""GTK 4 / libadwaita interface. The only module that imports gi."""

from __future__ import annotations

import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from .effects import EFFECTS, apply_text_rewrite, filter_chain  # noqa: E402
from .engine import Engine, EngineError  # noqa: E402
from .voices import Voice, discover, find  # noqa: E402

APP_ID = "nl.syntec.SynTalk"

_NO_EFFECT = "None"


class SynTalkWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application, title="SynTalk")
        self.set_default_size(900, 620)

        self._engine = Engine()
        self._voices: list[Voice] = discover()
        self._playback = None
        self._rows: dict[Gtk.ListBoxRow, Voice] = {}

        self._toasts = Adw.ToastOverlay()
        self.set_content(self._toasts)

        if not self._voices:
            self._toasts.set_child(self._build_empty_state())
            return

        self._toasts.set_child(self._build_split_view())
        self._select_voice_key(self._voices[0].key)

    # ---------------------------------------------------------------- layout

    def _build_empty_state(self) -> Gtk.Widget:
        page = Adw.StatusPage(
            icon_name="audio-speakers-symbolic",
            title="No voices installed",
            description=(
                "SynTalk looks for Piper voice models in\n"
                "~/.local/share/piper-voices\n\n"
                "Download one with:\n"
                "~/.local/share/piper-venv/bin/python -m piper.download_voices "
                "--data-dir ~/.local/share/piper-voices en_US-lessac-high"
            ),
        )
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(page)
        return view

    def _build_split_view(self) -> Gtk.Widget:
        split = Adw.NavigationSplitView()
        split.set_sidebar(self._build_sidebar())
        split.set_content(self._build_content())
        return split

    def _build_sidebar(self) -> Adw.NavigationPage:
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list.add_css_class("navigation-sidebar")
        self._list.connect("row-selected", self._on_voice_selected)

        for index, voice in enumerate(self._voices):
            row = Adw.ActionRow(title=voice.display_name,
                                subtitle=voice.language_label)
            if voice.is_multi_speaker:
                badge = Gtk.Label(label=f"{voice.num_speakers}")
                badge.add_css_class("dim-label")
                badge.add_css_class("caption")
                row.add_suffix(badge)
            self._list.append(row)
            self._rows[self._list.get_row_at_index(index)] = voice

        scroller = Gtk.ScrolledWindow(child=self._list, vexpand=True)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(scroller)
        return Adw.NavigationPage(child=view, title="Voices")

    def _build_content(self) -> Adw.NavigationPage:
        header = Adw.HeaderBar()
        save = Gtk.Button(icon_name="document-save-symbolic",
                          tooltip_text="Save as WAV")
        save.connect("clicked", self._on_save)
        header.pack_end(save)

        self._speaker_row = Adw.SpinRow.new_with_range(0, 0, 1)
        self._speaker_row.set_title("Speaker")
        self._speaker_group = Adw.PreferencesGroup()
        self._speaker_group.add(self._speaker_row)
        self._speaker_group.set_visible(False)

        self._buffer = Gtk.TextBuffer()
        text_view = Gtk.TextView(buffer=self._buffer,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 top_margin=12, bottom_margin=12,
                                 left_margin=12, right_margin=12)
        text_view.add_css_class("card")
        scroller = Gtk.ScrolledWindow(child=text_view, vexpand=True)

        self._effect_names = [_NO_EFFECT, *sorted(EFFECTS)]
        self._effect_drop = Gtk.DropDown.new_from_strings(self._effect_names)
        self._effect_drop.connect("notify::selected", self._on_effect_changed)

        self._speed = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.5, 2.0, 0.05)
        self._speed.set_value(1.0)
        self._speed.set_hexpand(True)
        self._speed.add_mark(1.0, Gtk.PositionType.BOTTOM, None)

        self._play = Gtk.Button()
        self._play.set_child(Adw.ButtonContent(label="Play",
                                               icon_name="media-playback-start-symbolic"))
        self._play.add_css_class("suggested-action")
        self._play.connect("clicked", self._on_play_clicked)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.append(Gtk.Label(label="Effect"))
        controls.append(self._effect_drop)
        controls.append(Gtk.Label(label="Speed"))
        controls.append(self._speed)
        controls.append(self._play)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_top=12, margin_bottom=12,
                       margin_start=12, margin_end=12)
        body.append(self._speaker_group)
        body.append(scroller)
        body.append(controls)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(body)

        shortcut = Gtk.ShortcutController()
        shortcut.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>Return"),
            Gtk.CallbackAction.new(self._on_shortcut_play),
        ))
        self.add_controller(shortcut)

        return Adw.NavigationPage(child=view, title="SynTalk")

    # ----------------------------------------------------------------- state

    def _selected_voice(self) -> Voice | None:
        return self._rows.get(self._list.get_selected_row())

    def _selected_effect(self):
        name = self._effect_names[self._effect_drop.get_selected()]
        return EFFECTS.get(name)

    def _select_voice_key(self, key: str) -> None:
        for row, voice in self._rows.items():
            if voice.key == key:
                self._list.select_row(row)
                return

    def _on_voice_selected(self, _list, row) -> None:
        voice = self._rows.get(row)
        if voice is None:
            return
        multi = voice.is_multi_speaker
        self._speaker_group.set_visible(multi)
        if multi:
            self._speaker_row.set_range(0, voice.num_speakers - 1)
            self._speaker_row.set_value(0)

    def _on_effect_changed(self, *_args) -> None:
        effect = self._selected_effect()
        if effect is None:
            return
        # Visible, undoable: the preset's own voice and speed are applied.
        self._select_voice_key(effect.voice_key)
        self._speed.set_value(effect.length_scale)

    def _text(self) -> str:
        start, end = self._buffer.get_bounds()
        return self._buffer.get_text(start, end, False)

    def _toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=5))

    # --------------------------------------------------------------- actions

    def _on_shortcut_play(self, *_args) -> bool:
        self._on_play_clicked(self._play)
        return True

    def _on_play_clicked(self, _button) -> None:
        if self._playback is not None:
            self._playback.stop()
            return

        voice = self._selected_voice()
        text = self._text()
        if voice is None or not text.strip():
            return

        effect = self._selected_effect()
        speaker_id = (int(self._speaker_row.get_value())
                      if voice.is_multi_speaker else None)

        self._play.set_sensitive(False)
        threading.Thread(
            target=self._play_worker,
            args=(voice, text, self._speed.get_value(), speaker_id, effect),
            daemon=True,
        ).start()

    def _play_worker(self, voice, text, length_scale, speaker_id, effect) -> None:
        try:
            if effect is not None:
                text = apply_text_rewrite(effect, text)
            pcm = self._engine.synthesize(
                voice, text, length_scale=length_scale, speaker_id=speaker_id)
            chain = (filter_chain(effect, voice.sample_rate)
                     if effect is not None else None)
            playback = self._engine.play(pcm, voice.sample_rate, chain=chain)
        except EngineError as exc:
            GLib.idle_add(self._playback_failed, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never kill the worker silently
            GLib.idle_add(self._playback_failed, f"unexpected error: {exc}")
            return

        GLib.idle_add(self._playback_started, playback)
        playback.wait()
        GLib.idle_add(self._playback_finished)

    def _playback_started(self, playback) -> bool:
        self._playback = playback
        self._play.set_child(Adw.ButtonContent(
            label="Stop", icon_name="media-playback-stop-symbolic"))
        self._play.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def _playback_finished(self) -> bool:
        self._playback = None
        self._play.set_child(Adw.ButtonContent(
            label="Play", icon_name="media-playback-start-symbolic"))
        self._play.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def _playback_failed(self, message: str) -> bool:
        self._playback = None
        self._play.set_sensitive(True)
        self._toast(message)
        return GLib.SOURCE_REMOVE

    def _on_save(self, _button) -> None:
        voice = self._selected_voice()
        if voice is None or not self._text().strip():
            return
        dialog = Gtk.FileDialog(initial_name="syntalk.wav")
        dialog.save(self, None, self._on_save_chosen)

    def _on_save_chosen(self, dialog, result) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # user cancelled
        if gfile is None:
            return
        # Read every widget here, on the main loop. The worker must not touch GTK.
        voice = self._selected_voice()
        if voice is None:
            return
        args = (
            gfile.get_path(),
            voice,
            self._text(),
            self._selected_effect(),
            self._speed.get_value(),
            int(self._speaker_row.get_value()) if voice.is_multi_speaker else None,
        )
        threading.Thread(target=self._save_worker, args=args, daemon=True).start()

    def _save_worker(self, path, voice, text, effect, length_scale,
                     speaker_id) -> None:
        try:
            if effect is not None:
                text = apply_text_rewrite(effect, text)
            pcm = self._engine.synthesize(
                voice, text, length_scale=length_scale, speaker_id=speaker_id)
            chain = (filter_chain(effect, voice.sample_rate)
                     if effect is not None else None)
            self._engine.save_wav(pcm, voice.sample_rate, path, chain=chain)
        except Exception as exc:  # noqa: BLE001 - surfaced as a toast
            GLib.idle_add(self._toast, f"could not save: {exc}")
            return
        GLib.idle_add(self._toast, f"Saved {path}")


class SynTalkApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window or SynTalkWindow(self)
        window.present()
```

- [ ] **Step 2: Implement the entry point**

Create `src/syntalk/__main__.py`:

```python
"""Console entry point."""

from __future__ import annotations

import sys


def main() -> int:
    from .gui import SynTalkApp

    return SynTalkApp().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Verify the GTK-free boundary still holds**

Run:

```bash
grep -rln "import gi" src/syntalk/
```

Expected: exactly one line, `src/syntalk/gui.py`. Any other file is a defect —
fix it before continuing.

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: PASS, all tests from Tasks 1-3 still green.

- [ ] **Step 5: Launch it**

Run: `.venv/bin/syntalk`

Confirm before continuing:
1. The window opens with 8 voices in the sidebar, each showing its language.
2. VCTK shows a `109` badge, L2Arctic shows `24`.
3. Typing text and clicking **Play** produces audio.
4. Selecting VCTK reveals the Speaker spinner, capped at 108.
5. Choosing the `demon` effect moves the sidebar selection to Lessac and the
   speed slider to 1.25.
6. `Ctrl+Return` plays.

- [ ] **Step 6: Commit**

```bash
printf '0.1.6\n' > VERSION
sed -i 's/^\*\*Version:\*\* .*/**Version:** 0.1.6/' README.md
git add -A
git commit -m "$(cat <<'EOF'
feat: GTK 4 interface v0.1.6

Adw.NavigationSplitView with a voice sidebar, large text field, effect
dropdown, speed slider and a play/stop toggle. Synthesis runs off the
main loop; failures surface as toasts.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin dev
```

---

### Task 5: Desktop launcher, icon and install script

**Files:**
- Create: `data/nl.syntec.SynTalk.desktop`
- Create: `data/icons/hicolor/scalable/apps/nl.syntec.SynTalk.svg`
- Create: `install.sh`
- Create: `uninstall.sh`
- Modify: `README.md`, `VERSION`

**Interfaces:**
- Consumes: the `syntalk` console script produced by Task 1's `pyproject.toml`.
- Produces: nothing other code imports.

- [ ] **Step 1: Create the icon**

Create `data/icons/hicolor/scalable/apps/nl.syntec.SynTalk.svg` — a speech bubble
containing a soundwave, flat colours, drawn on the 128×128 GNOME grid:

```svg
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <rect x="8" y="8" width="112" height="112" rx="26" fill="#3584e4"/>
  <path d="M28 34h72a10 10 0 0 1 10 10v34a10 10 0 0 1-10 10H62l-20 18v-18h-14a10 10 0 0 1-10-10V44a10 10 0 0 1 10-10z"
        fill="#ffffff"/>
  <g stroke="#3584e4" stroke-width="6" stroke-linecap="round">
    <line x1="40" y1="55" x2="40" y2="67"/>
    <line x1="52" y1="48" x2="52" y2="74"/>
    <line x1="64" y1="42" x2="64" y2="80"/>
    <line x1="76" y1="48" x2="76" y2="74"/>
    <line x1="88" y1="55" x2="88" y2="67"/>
  </g>
</svg>
```

Verify it renders at small size:

```bash
rsvg-convert -w 32 -h 32 data/icons/hicolor/scalable/apps/nl.syntec.SynTalk.svg \
  -o /tmp/icon32.png 2>/dev/null && echo "rendered" || echo "rsvg-convert absent, skipping"
```

- [ ] **Step 2: Create the desktop entry**

Create `data/nl.syntec.SynTalk.desktop`. `Exec` is a placeholder that `install.sh`
rewrites to the venv's absolute path:

```ini
[Desktop Entry]
Type=Application
Name=SynTalk
GenericName=Text to Speech
Comment=Local neural text-to-speech
Exec=syntalk
Icon=nl.syntec.SynTalk
Terminal=false
Categories=AudioVideo;Audio;Utility;
Keywords=tts;speech;voice;piper;say;
StartupNotify=true
StartupWMClass=nl.syntec.SynTalk
```

- [ ] **Step 3: Write `install.sh`**

Create `install.sh` (then `chmod +x install.sh`):

```bash
#!/usr/bin/env bash
# Install SynTalk into a local venv and register the desktop launcher.
# Idempotent. No sudo. Re-run after pulling changes.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="nl.syntec.SynTalk"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

cd "$PROJECT_DIR"

command -v uv >/dev/null || { echo "install: uv is required" >&2; exit 1; }

# PyGObject comes from the system; the venv must be able to see it.
echo "==> creating venv"
uv venv --system-site-packages

echo "==> installing syntalk"
uv pip install -e .

BIN="$PROJECT_DIR/.venv/bin/syntalk"
[[ -x $BIN ]] || { echo "install: $BIN missing after install" >&2; exit 1; }

echo "==> verifying runtime"
"$PROJECT_DIR/.venv/bin/python" -c "
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk
from piper import PiperVoice
print('   GTK', Gtk.get_major_version(), Gtk.get_minor_version(), '+ libadwaita + piper OK')
"

for tool in ffmpeg aplay; do
  command -v "$tool" >/dev/null || echo "   warning: $tool not found; some features will fail"
done

echo "==> installing launcher"
mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
sed "s|^Exec=.*|Exec=$BIN|" "data/$APP_ID.desktop" > "$DESKTOP_DIR/$APP_ID.desktop"
cp "data/icons/hicolor/scalable/apps/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$DESKTOP_DIR"
else
  echo "   note: update-desktop-database absent, skipped"
fi

if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
else
  echo "   note: gtk-update-icon-cache absent, skipped"
fi

echo
echo "SynTalk installed. Launch it from the GNOME overview, or run:"
echo "  $BIN"
```

- [ ] **Step 4: Write `uninstall.sh`**

Create `uninstall.sh` (then `chmod +x uninstall.sh`):

```bash
#!/usr/bin/env bash
# Remove the SynTalk launcher and icon. Leaves the project and venv alone.
set -euo pipefail

APP_ID="nl.syntec.SynTalk"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"

rm -fv "$DESKTOP_FILE" "$ICON_FILE"

command -v update-desktop-database >/dev/null \
  && update-desktop-database "$HOME/.local/share/applications"
command -v gtk-update-icon-cache >/dev/null \
  && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "SynTalk launcher removed."
```

- [ ] **Step 5: Run the installer and validate the desktop entry**

Run:

```bash
./install.sh
desktop-file-validate ~/.local/share/applications/nl.syntec.SynTalk.desktop \
  && echo "desktop entry valid"
```

Expected: install completes, `desktop entry valid` prints. If
`desktop-file-validate` is not installed, skip it and note that in the report.

- [ ] **Step 6: Update the README**

Replace the body of `README.md` with:

````markdown
# SynTalk

**Version:** 0.1.7

Local neural text-to-speech with a GTK 4 interface. Pick a voice, type, press play.
Everything runs offline on your own machine.

## Requirements

- Python 3.12+
- System PyGObject with GTK 4 and libadwaita (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`)
- `ffmpeg` and `aplay` (alsa-utils)
- [`uv`](https://docs.astral.sh/uv/)
- At least one Piper voice in `~/.local/share/piper-voices`

## Install

```bash
./install.sh
```

This creates a venv (with `--system-site-packages`, so `gi` resolves), installs
SynTalk into it, and registers the launcher and icon. Then find **SynTalk** in the
GNOME overview.

`./uninstall.sh` removes the launcher and icon.

## Use

- Pick a voice in the sidebar. Multi-speaker voices show a speaker selector.
- Type into the text field. **Play**, or `Ctrl+Return`.
- **Effect** applies a character preset — it also switches to the voice that preset
  was tuned for, and sets the matching speed. Change either afterwards if you like.
- The save button in the header writes the current text to a WAV file.

## Downloading more voices

```bash
~/.local/share/piper-venv/bin/python -m piper.download_voices \
  --data-dir ~/.local/share/piper-voices en_US-ryan-high
```

SynTalk discovers whatever is in that directory at launch. 171 voices across 53
languages are available.

## Development

```bash
uv venv --system-site-packages
uv pip install -e . --group dev
.venv/bin/pytest
```

`voices.py`, `effects.py` and `engine.py` import no GTK. `gui.py` is the only
module that touches `gi` — that boundary keeps a future CLI cheap.

## Branches

- `master` — stable / released code
- `dev` — active development (all work happens here)

## Versioning

Semantic versioning. Patch version increments on every commit to `dev`.
Minor and major bumps are merged from `dev` into `master`.
````

- [ ] **Step 7: Full manual smoke test**

Work through spec §6 and record the result of each:

1. Launch from the GNOME overview by searching "SynTalk"; the icon renders.
2. All 8 voices listed with correct language labels.
3. Type, press Play, audio plays on the default voice.
4. Select VCTK; speaker spinner appears, capped at 108; play speaker 42.
5. Select `demon`; sidebar jumps to Lessac, speed to 1.25; play.
6. Select `yoda`; sidebar jumps to Alan; spoken word order is rearranged.
7. Play long text, press Stop mid-utterance; audio ceases immediately.
8. Save WAV with an effect applied; play the file back, effect is present.

Any failure here is a bug to fix before the final commit, not something to report
as a known issue.

- [ ] **Step 8: Run the full test suite one more time**

Run: `.venv/bin/pytest -v`
Expected: PASS, everything green.

- [ ] **Step 9: Commit**

```bash
printf '0.1.7\n' > VERSION
git add -A
git commit -m "$(cat <<'EOF'
feat: desktop launcher, icon and installer v0.1.7

Speech-bubble SVG icon on the GNOME grid, validated .desktop entry, and
an idempotent install.sh that builds the system-site-packages venv and
registers both. README rewritten for the GUI.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin dev
```

---

## Done means

- `.venv/bin/pytest` green.
- `grep -rln "import gi" src/syntalk/` returns only `gui.py`.
- All 8 manual smoke-test steps pass, with the actual observed result reported.
- `dev` pushed at 0.1.7.

A minor bump to 0.2.0 (CHANGELOG.md, README update, merge `dev` → `master`) is a
separate action, taken only when asked.
