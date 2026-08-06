# Changelog

All notable changes to SynTalk are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] — 2026-08-06

First feature-complete release. SynTalk replaces the `say` and `sayfx` bash
prototypes with a GTK 4 desktop application.

### Added

- **Voice sidebar.** Every Piper voice found in `~/.local/share/piper-voices` is
  discovered at launch — no hardcoded list. Each row shows the voice name and a
  language label derived from the model's own metadata, so voices downloaded later
  label themselves correctly. Multi-speaker models carry a speaker-count badge.
- **Speaker selector.** Multi-speaker voices get a spinner clamped to their valid
  range, reset on every voice change, so an out-of-range speaker id cannot reach
  synthesis.
- **Next-speaker button.** Visible only for multi-speaker voices. Advances to the
  next speaker — wrapping back to the first past the last — and immediately plays
  the current text. Auditioning VCTK's 109 speakers is one repeated click.
- **Ten character effects**, transcribed verbatim from `reference/sayfx`: `yoda`,
  `robot`, `chipmunk`, `demon`, `giant`, `ghost`, `radio`, `drunk`, `announcer`,
  `tiny`. The `yoda` preset also rewrites the sentence into Yoda word order before
  synthesis.
- **Collapsible session log.** Every play, next-speaker play, save and failure
  appends a timestamped entry recording the text spoken and an equivalent,
  genuinely copy-pasteable shell command. Copy puts the whole log on the clipboard;
  Clear empties it. Never truncated automatically.
- **Save to WAV**, with the current voice, speaker, length and effect applied.
- **Desktop integration.** An SVG icon and a validated `.desktop` entry install to
  `~/.local/share`, so SynTalk appears in the GNOME overview. `install.sh` is
  idempotent and verifies the runtime before finishing; `uninstall.sh` reverses it.
- `Ctrl+Return` plays.

### Architecture

- `voices.py`, `effects.py`, `engine.py` and `commandline.py` import no GTK.
  `gui.py` is the only module that touches `gi` — a boundary enforced by a test,
  not by review discipline. This keeps the CLI described in `HANDOFF.md` a thin
  later addition rather than a rewrite.
- Piper models are loaded once and cached; repeated utterances in a voice skip the
  load entirely.
- PCM is streamed into `ffmpeg` on stdin rather than through a temp WAV file, which
  is what the `sayfx` prototype did.
- The sample rate always comes from the voice's own `.json`. There is no default
  anywhere in the source, and a test enforces that.

### Fixed

Defects found and closed during development, listed because each was reachable by
an ordinary user action:

- **Playback was killed 10 seconds in.** `Playback.wait()` used a single 10-second
  timeout both to await normal completion and to bound a hung stop, so `aplay` was
  SIGKILLed partway through any utterance longer than about 25 words — silently,
  with no error and no visible difference from finishing normally. `wait()` now
  blocks unbounded; the deadline applies only to `stop()`. Covered by a regression
  test that plays 15 seconds of real audio.
- **`Ctrl+Return` could start overlapping playbacks.** The keyboard shortcut
  bypassed the Play button's disabled state, so two quick presses during synthesis
  started two audio streams and orphaned the first beyond reach of the Stop button.
  An explicit busy flag now guards every entry point; button sensitivity is no
  longer load-bearing.
- **A double-click on Save could corrupt the output.** With no guard and no progress
  feedback, a second click ran a second `ffmpeg -y` against the same path and
  reported two successes over a damaged file. Save is now guarded and reports when
  it starts.
- **The empty state pointed at a venv that never exists** on a fresh install, so the
  first screen a new user saw handed them a command that could not work.
- **A failed playback left the button reading "Stop"** with nothing playing, so the
  next click started a new synthesis instead of stopping.
- **`update-desktop-database` could abort `uninstall.sh`** after the files were
  already removed, reporting failure for an uninstall that had worked.
- **`StartupWMClass` did not match the real window class**, so GNOME could not
  reliably associate the running window with its launcher.
- The speed slider was labelled "Speed" while driving Piper's length scale, where a
  higher value is *slower*. Relabelled to "Length" with a tooltip.

### Known limitations

- Synthesis is not streamed: the whole utterance is generated before playback
  begins, so a page of text means roughly 30 seconds of silence first, and playback
  cannot be cancelled until it starts. Roughly 2.65 MB of memory per minute of audio.
- The empty-state download command is project-root-relative and needs adjusting if
  the app was launched from the GNOME overview.
- No CLI yet. The core modules are GTK-free specifically to make that cheap.
- Voice cloning is out of scope — it needs a different model class entirely.

---

## [0.1.0] — 2026-08-05

- Initial repository scaffold.
