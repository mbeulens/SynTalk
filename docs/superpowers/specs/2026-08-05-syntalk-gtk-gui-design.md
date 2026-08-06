# SynTalk — GTK 4 GUI Design

**Date:** 2026-08-05
**Status:** Approved
**Supersedes:** nothing. Extends `HANDOFF.md`.

---

## 1. Goal

A simple GTK 4 desktop application for local neural text-to-speech: pick a voice from a
sidebar, type into a large text field, press play. Ships with a desktop launcher and icon
so it appears in the GNOME activities overview.

The synthesis logic lives in GTK-free modules so the CLI described in `HANDOFF.md` can be
added later as a thin layer over the same core.

### Out of scope

- The `say` / `sayfx` CLI replacement. Deferred; the core is designed to make it small.
- Voice cloning (Chatterbox, XTTS-v2, F5-TTS). Deferred per `HANDOFF.md` §5.
- Downloading new voices from within the GUI. The app reads what is already on disk.
- Editing or creating effect presets from the GUI. Presets are code.

---

## 2. Environment

Verified on this machine (2026-08-05):

| Component | Version / location |
|---|---|
| GTK | 4.14 (system PyGObject, `python3-gi`) |
| libadwaita | 1.x, importable as `Adw` |
| Session | GNOME on X11 |
| Piper | 1.6.0 in `~/.local/share/piper-venv/` |
| Voices | 8 models in `~/.local/share/piper-voices/` |
| ffmpeg | `/usr/bin/ffmpeg` |
| aplay | alsa-utils |
| uv | 0.11.15 |

**PyGObject is a system package and is not pip-installable here.** The project venv is
therefore created with `uv venv --system-site-packages`, and `piper-tts` is installed into
it. `gi` resolves from the system, `piper` from the venv.

Everything is offline at runtime. No network calls.

---

## 3. Architecture

```
SynTalk/
├─ pyproject.toml
├─ src/syntalk/
│   ├─ __init__.py
│   ├─ voices.py       voice discovery and metadata
│   ├─ effects.py      character effect presets
│   ├─ engine.py       synthesis, effects application, playback, WAV export
│   ├─ gui.py          GTK 4 / libadwaita interface
│   └─ __main__.py     entry point
├─ data/
│   ├─ nl.syntec.SynTalk.desktop
│   └─ icons/hicolor/scalable/apps/nl.syntec.SynTalk.svg
├─ tests/
│   ├─ test_voices.py
│   └─ test_effects.py
├─ install.sh
├─ reference/           verbatim bash prototypes, do not edit
└─ docs/
```

`voices.py`, `effects.py` and `engine.py` import no GTK. `gui.py` is the only module that
imports `gi`. This boundary is what keeps the future CLI cheap.

### 3.1 `voices.py`

Discovers installed voices. No hardcoded voice list.

```python
@dataclass(frozen=True)
class Voice:
    model_path: Path        # …/en_GB-vctk-medium.onnx
    key: str                # "en_GB-vctk-medium"
    display_name: str       # "VCTK"
    language_code: str      # "en_GB"
    language_label: str     # "English (UK)"
    sample_rate: int        # from meta["audio"]["sample_rate"]
    num_speakers: int       # from meta["num_speakers"]
    speaker_names: list[str]  # keys of meta["speaker_id_map"], index-ordered

def discover(voices_dir: Path = DEFAULT_VOICES_DIR) -> list[Voice]
def find(key: str, voices: list[Voice]) -> Voice | None
```

- Scans `*.onnx`, reads the sibling `<model>.onnx.json`.
- A model whose `.json` is missing or unparseable is skipped, not fatal — it is reported
  to the caller through the returned list simply not containing it, and logged to stderr.
- `display_name` is derived from the key: strip the language prefix and the quality
  suffix, replace `_` with a space, title-case. `en_GB-northern_english_male-medium`
  becomes `Northern English Male`.
- `language_label` is built from the voice's own metadata —
  `language.name_english` + `language.country_english`, giving
  `English (Great Britain)`, `Dutch (Belgium)` and so on — falling back to
  `language.code` when either field is absent. No static map, so voices downloaded
  later label themselves correctly.
- Sorting: by `language_label`, then `display_name`.

### 3.2 `effects.py`

The ten presets from `reference/sayfx`, transcribed verbatim.

```python
@dataclass(frozen=True)
class Effect:
    name: str            # "yoda"
    voice_key: str       # "en_GB-alan-medium"
    length_scale: float  # 1.45
    chain: str           # raw chain with @SR@ placeholders
    rewrites_text: bool  # True only for yoda

EFFECTS: dict[str, Effect]

def filter_chain(effect: Effect, sample_rate: int) -> str
def apply_text_rewrite(effect: Effect, text: str) -> str
```

- `filter_chain` substitutes `@SR@` with the sample rate, then **splits any `atempo`
  value outside 0.5–2.0 into a chain of in-range `atempo` instances** whose product equals
  the requested value. The bash prototype never hit this limit with its own presets, but
  the pitch-shift idiom makes it reachable, so the split is implemented and tested.
- `apply_text_rewrite` implements the yoda word-order transform from `reference/sayfx`
  lines 56–64: split on `[.!?]+`, for each clause with ≥4 words move the second half to
  the front and append `, yes`, rejoin with `. `. Clauses under 4 words pass through
  unchanged.
- Effects with `rewrites_text=False` return the text untouched.

### 3.3 `engine.py`

```python
class Engine:
    def __init__(self) -> None                      # empty model cache
    def synthesize(self, voice, text, *, length_scale, speaker_id) -> bytes
    def play(self, pcm, sample_rate, *, chain=None) -> Playback
    def save_wav(self, pcm, sample_rate, path, *, chain=None) -> None
```

**Streaming playback (added 2026-08-06, v0.2.1).** `synthesize()` accumulates the whole
utterance before a single sample plays, so a page of text meant ~30 s of silence that
could not be cancelled. `speak()` supersedes it for the playback path:

```python
def speak(self, voice, text, *, length_scale=1.0, speaker_id=None,
          chain=None) -> Playback
```

- Validates the text and `speaker_id`, and loads the model, **before** spawning
  anything — so an invalid speaker id or a failed model load still raises `EngineError`
  before any audio starts, exactly as before.
- Spawns the `aplay` (and optional `ffmpeg`) pipeline immediately, using
  `voice.sample_rate`, which is known up front from the `.json`.
- A feeder thread iterates `model.synthesize(...)` and writes each
  `chunk.audio_int16_bytes` to the sink as it is produced. Audio starts after the first
  chunk rather than the last.
- `Playback` gains a `threading.Event` cancel flag, checked between chunks and set by
  `stop()` — **Stop now interrupts synthesis**, not just playback. It also gains
  `error: EngineError | None`, recording a failure raised mid-stream so the GUI can
  toast it after `wait()` returns. `wait()` joins the feeder before reaping, so `error`
  is always settled by the time it returns.
- Memory no longer scales with utterance length; only the in-flight chunk is held.

`synthesize()` remains, buffered, for Save — nothing is waiting to hear a file being
written — and `play()` remains for callers that already hold PCM, both sharing the
pipeline-spawning helper with `speak()`.

- Models are cached in a `dict[Path, PiperVoice]`. A voice is loaded once per process;
  repeat utterances skip the load.
- `synthesize` concatenates `chunk.audio_int16_bytes` from `voice.synthesize()` into a
  single `bytes`. CPU inference (`use_cuda=False`) — `onnxruntime-gpu` is not installed.
- `play` returns a `Playback` handle wrapping the live `subprocess.Popen` objects, with
  `.stop()` (terminate both) and `.wait()`.
- Pipeline with no effect: PCM → `aplay -q -r <SR> -f S16_LE -t raw -`.
- Pipeline with an effect: PCM → `ffmpeg -v error -f s16le -ar <SR> -ac 1 -i - -af <chain>
  -f wav -` → `aplay -q -`. ffmpeg reads raw PCM on stdin; no temp files, unlike the bash
  prototype.
- `save_wav` writes via ffmpeg when a chain is set, otherwise via the `wave` module.
- Missing `ffmpeg` or `aplay` raises `EngineError` with a message naming the tool.

### 3.4 `gui.py`

`Adw.Application` with one `Adw.ApplicationWindow` containing an
`Adw.NavigationSplitView`.

```
┌─ Voices ──────────┬─ SynTalk ──────────────────── [Save WAV] ─┐
│ ● Lessac    US    │  Speaker  [ 42 ]   (multi-speaker only)   │
│   Alan      GB    │  ┌────────────────────────────────────┐   │
│   Cori      GB    │  │                                    │   │
│   N.English GB    │  │  type anything here…               │   │
│   VCTK      GB ¹⁰⁹│  │                                    │   │
│   L2Arctic  US ²⁴ │  └────────────────────────────────────┘   │
│   Nathalie  BE    │  Effect [None ▾] Speed ─●─ [⏭][▶ Play]   │
│   Pim       NL    │            next-speaker ⏭ multi-spk only  │
└───────────────────┴───────────────────────────────────────────┘
```

**Sidebar** — `Gtk.ListBox` of `Adw.ActionRow`, one per discovered voice: title is
`display_name`, subtitle is `language_label`, and multi-speaker voices carry a suffix
label showing the speaker count. Selection drives everything else.

**Speaker control** — an `Adw.SpinRow` bound to `0 … num_speakers - 1`, visible only when
the selected voice has more than one speaker. Resets to 0 on voice change. Guarantees a
valid `speaker_id`, so synthesis never errors on an out-of-range id.

**Text field** — `Gtk.TextView` with `wrap_mode=WORD_CHAR` inside a `Gtk.ScrolledWindow`,
expanding to fill. `Ctrl+Return` triggers play.

**Bottom bar** — `Gtk.DropDown` for the effect (`None` plus the ten presets), a
`Gtk.Scale` for speed (0.5–2.0, step 0.05, default 1.0, marked at 1.0), and the play
button.

**Effect ↔ voice coupling — none.** Selecting an effect applies that preset's filter
chain to **whatever voice the user has selected**, and sets the speed slider to the
preset's `length_scale` (the speed is part of the effect's character). The sidebar
selection is never changed by an effect. Revised 2026-08-06 after use: the original
design moved the selection to the preset's tuned voice, which meant every effect change
silently discarded the user's voice choice and forced them to reselect it.

**Play button** — label `Play` with a play icon; while audio is running it becomes `Stop`
with a stop icon and calls `Playback.stop()` on a worker thread.

**Next-speaker button** — visible only when the selected voice is multi-speaker. Advances
the speaker spinner by one, wrapping back to 0 past the last speaker, and immediately
plays the current text with that speaker. This makes auditioning VCTK's 109 speakers a
single repeated click rather than a spin-then-play cycle.

**Busy guard.** A single `_busy` flag — not button sensitivity — gates every entry point
into playback (Play button, next-speaker button, `Ctrl+Return`). Sensitivity is a view
concern and keyboard shortcuts bypass it, so it cannot be the invariant.

**Save WAV** — a header-bar button opening `Gtk.FileDialog`, writing the current text with
the current settings via `Engine.save_wav`.

**Threading.** Synthesis and playback run on a `threading.Thread`. All UI mutation is
marshalled back with `GLib.idle_add`; worker threads never read or write a widget —
`_on_save_chosen` snapshots every widget value on the main loop before spawning. Exactly
one playback is active at a time, enforced by the `_busy` flag above. `Ctrl+Return`
during playback stops it, matching the button's current state.

**Empty state.** If `discover()` returns nothing, the split view is replaced by an
`Adw.StatusPage` explaining where voices are expected and how to download one, and the
play controls are insensitive.

---

## 4. Error handling

| Condition | Behaviour |
|---|---|
| Blank / whitespace-only text | Silent no-op. No synthesis, no toast. |
| No voices found | `Adw.StatusPage` empty state, controls disabled. |
| Voice `.json` missing or invalid | That voice is skipped at discovery, warning to stderr. |
| `ffmpeg` or `aplay` missing | `Adw.Toast` naming the missing tool; nothing crashes. |
| Synthesis raises | `Adw.Toast` with the message; UI returns to idle. |
| Playback killed via Stop | No toast. Normal path. |
| Save WAV fails | `Adw.Toast` with the reason. |

All user-facing failures are toasts. The application never exits on a recoverable error.

---

## 5. Desktop integration

**Icon** — `data/icons/hicolor/scalable/apps/nl.syntec.SynTalk.svg`, hand-authored SVG on
the GNOME 128×128 icon grid: a rounded speech bubble containing a soundwave. Flat colours,
no gradients, legible at 32px.

**Desktop entry** — `data/nl.syntec.SynTalk.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=SynTalk
Comment=Local neural text-to-speech
Exec=<install-prefix>/bin/syntalk
Icon=nl.syntec.SynTalk
Terminal=false
Categories=AudioVideo;Audio;Utility;
Keywords=tts;speech;voice;piper;
StartupNotify=true
```

**`install.sh`** — idempotent, no sudo:

1. `uv venv --system-site-packages` and `uv pip install -e .` in the project directory.
2. Copy the `.desktop` file to `~/.local/share/applications/`, rewriting `Exec=` to the
   absolute path of the venv's `syntalk` entry point.
3. Copy the icon to `~/.local/share/icons/hicolor/scalable/apps/`.
4. `update-desktop-database ~/.local/share/applications` and
   `gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor`, each skipped with a notice
   if the tool is absent.

Re-running overwrites cleanly. An `uninstall.sh` removes the two installed files.

---

## 6. Testing

**Automated** (`pytest`, no audio hardware, no GTK):

- `test_voices.py` — discovery against a fixture directory of stub `.onnx` + `.json`
  pairs: correct count, metadata parsing, `display_name` derivation for each real voice
  key, skipping of a model with a malformed `.json`, sort order, `find()` hit and miss.
- `test_effects.py` — `@SR@` substitution for a non-22050 rate, `atempo` splitting for
  values above 2.0 and below 0.5 (product equals the requested factor), yoda rewrite on
  multi-sentence input, short-clause passthrough, non-rewriting effects returning input
  unchanged, and that all ten preset `voice_key`s name a voice that exists on disk.

**Manual smoke test**, run and reported before the work is called done:

1. Launch, confirm all 8 voices listed with correct languages.
2. Type, press Play, hear audio on the default voice.
3. Select VCTK, confirm the speaker spinner appears and is capped at 108; play speaker 42.
4. Select the `demon` effect, confirm the sidebar selection is unchanged and the length
   slider moves to 1.25, play.
5. Select `yoda`, confirm the sidebar selection is still unchanged and the spoken word
   order is rearranged.
6. Press Play on long text, then Stop mid-utterance; audio ceases immediately.
7. Save WAV with an effect applied; play the file back and confirm the effect is present.
8. Launch from the GNOME overview by searching "SynTalk"; confirm the icon renders.

---

## 7. Open risks

- **Piper Python API drift.** The API in `HANDOFF.md` §4 is verified against 1.6.0 on this
  machine and is pinned in `pyproject.toml` as `piper-tts>=1.6,<2`.
- **`aplay` device contention.** If another application holds the ALSA device, playback
  fails. This surfaces as a toast rather than being handled — acceptable for a local tool.
- **X11 vs Wayland.** Nothing in the design is display-server specific; only X11 is
  tested here.
