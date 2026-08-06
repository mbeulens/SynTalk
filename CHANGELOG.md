# Changelog

All notable changes to SynTalk are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.2] — 2026-08-06

### Fixed

- **`Playback.stop()` closed the pipeline's `stdin` too late.** `aplay` (and, with
  an effect chain, `ffmpeg`) does not always react promptly to `SIGTERM` while its
  stdin is still open and being written to by the feeder thread, so `stop()` could
  ride the full 10s grace period and fall back to `SIGKILL` on every Stop, not just
  on a genuinely wedged device. `Playback` now holds the pipeline's sink and closes
  it in `stop()` *before* terminating the processes: closing hands the reader EOF,
  so it drains whatever is already buffered and exits on its own well inside the
  10s bound. The feeder threads already tolerated `BrokenPipeError`/`ValueError`/
  `OSError` from a write racing this close, so no feeder change was needed. The 10s
  bound remains as the genuine wedged-device backstop; it should no longer be the
  normal path. `wait()` is unaffected and stays unbounded.
- `VERSION` is restored to end with a trailing newline (lost in the 0.2.1 commit).

### Added

- Two regression tests assert `Playback.stop()` returns well under the 10s bound
  (a 2s ceiling) for both the aplay-only pipeline and the two-process
  ffmpeg-into-aplay pipeline an effect uses, feeding audio faster than real-time
  playback can drain it to keep the pipe genuinely busy while stopping.

---

### Known limitation, measured

Streaming granularity is one Piper chunk, and Piper splits only where espeak sees a
sentence boundary — which requires a capital letter after the full stop, or a line
break. Normally punctuated prose starts in ~0.39 s regardless of length and Stop
interrupts within a sentence. All-lower-case or unpunctuated text is synthesised as a
single chunk and behaves as it did before streaming: silence until ready, and Stop
cannot interrupt it. This is a property of Piper's sentence splitting, not of SynTalk;
it is documented rather than worked around, because pre-splitting text ourselves would
mis-split abbreviations like "Dr. Smith" into unnatural pauses.

## [0.2.1] — 2026-08-06

### Added

- **Streaming playback.** `Engine.speak()` supersedes buffered `synthesize()` +
  `play()` on the Play path: it validates the text and speaker id and loads the model
  first (so a bad speaker id or a failed model load still raises before any audio
  starts), then spawns the `aplay` (and, with an effect, `ffmpeg`) pipeline immediately
  and streams each synthesis chunk into it as Piper produces it. A page of text now
  starts playing after the first chunk instead of after the whole utterance is
  generated, and memory no longer scales with utterance length.
- **Stop now interrupts synthesis, not just playback.** `Playback` gains a cancel
  flag checked between chunks; `stop()` sets it before terminating the pipeline, so a
  long utterance stops promptly instead of finishing generation in the background.
- **Mid-stream synthesis failures are surfaced.** `Playback.error` records an
  `EngineError` raised partway through streaming; the GUI toasts it and logs the
  failure once `wait()` returns, instead of failing silently on the feeder thread.

### Fixed

- The empty-state "no voices installed" screen now builds its download command from
  `sys.executable` instead of a hardcoded `.venv/bin/python`, so the command works
  when SynTalk is launched from the GNOME overview (working directory `$HOME`), not
  just from the project root.

### Changed

- `synthesize()` and `play()` remain, unchanged, for the Save-to-WAV path and for
  callers that already hold PCM; both now share pipeline-spawning code with `speak()`.

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
