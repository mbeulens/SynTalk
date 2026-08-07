# Changelog

All notable changes to SynTalk are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.0] — 2026-08-07

A TARS character preset, a clipping bug that turned out to affect three presets, and
a copy-paste command that could never actually be pasted.

### Added

- **`tars` character preset** (Interstellar). Deliberately the least processed preset
  in the file: TARS reads as a person, not a machine, so there is no vibrato, flanger
  or bit crushing. The character comes from a −6 % pitch drop, a 120–7000 Hz band limit
  that says "reproduced through a speaker", a midrange box resonance, hard levelling,
  and one 13 ms reflection off the hull. Base voice is
  `en_GB-northern_english_male-medium`, chosen by ear: the deadpan of the performance
  matters more than matching TARS's American accent, and a medium-tier model is the
  one that stays real-time on a Raspberry Pi.

### Fixed

- **Three presets clipped in 16-bit.** Piper normalises its output to 0 dBFS, so any
  EQ boost or filter overshoot clips *in place* before a downstream compressor or
  limiter can act on it. `aformat=sample_fmts=fltp` at the head of a chain gives the
  intermediate stages float headroom. That alone fixed `radio` (4 clipped samples → 0)
  but made `tiny` worse (24 → 44) — float removed the accidental clamping the integer
  path had been providing — so `tiny` also gains a limiter to catch the `highpass`
  overshoot. **All eleven presets now render zero clipped samples.**
- **`commandline.py` emitted a command that could not be run.** Its documented purpose
  is producing a string the user can paste into a terminal, but it emitted a bare
  `piper` token. Piper is installed into the same venv as SynTalk and is essentially
  never on `PATH`, so the command failed with `Command 'piper' not found` for every
  venv install — and Ubuntu then suggests `apt install piper`, which is an unrelated
  gaming-mouse configuration tool. The console script is now resolved next to
  `sys.executable`, as the empty-state download hint already does, falling back to the
  bare name for system-wide installs where `PATH` is correct.
- **Two ffmpeg parameter mistakes**, found while building the preset and worth
  recording because both fail silently as "it just got quieter": `aecho`'s second
  parameter is `out_gain`, a flat output level, not the reflection mix (the mix is the
  trailing parameter); and `acompressor` defaults to `makeup=1`, i.e. none, so a
  compressor without an explicit makeup gain is a pure attenuator.

---

## [0.3.0] — 2026-08-07

Streaming playback. Long text now starts speaking almost immediately instead of after
the whole utterance is generated, and Stop interrupts the synthesis itself.

Released as one entry: 0.2.1 through 0.2.3 existed only on `dev` and never shipped.

### Added

- **Streaming playback.** `Engine.speak()` supersedes buffered `synthesize()` +
  `play()` on the Play path. It validates the text and speaker id and loads the model
  first — so a bad speaker id or a failed model load still raises before any audio
  starts — then spawns the `aplay` (and, with an effect, `ffmpeg`) pipeline immediately
  and streams each chunk into it as Piper produces it. Measured on ~400 words of
  ordinary prose: **16.6 s of silence before, 0.39 s after.** Memory no longer scales
  with utterance length.
- **Stop interrupts synthesis, not just playback.** `Playback` gains a cancel flag
  checked between chunks. Stopping a long utterance now abandons the remaining
  generation instead of finishing it in the background — measured at ~15 s of CPU work
  abandoned on a 400-word text.
- **Mid-stream synthesis failures are surfaced.** `Playback.error` records an
  `EngineError` raised partway through streaming; the GUI toasts and logs it once
  `wait()` returns, instead of the feeder thread dying silently after partial audio.
- Regression tests asserting `stop()` returns well under its 10 s bound on both the
  one-process and two-process pipelines, feeding audio faster than real-time playback
  drains it so the pipe is genuinely busy while stopping.

### Fixed

- **`stop()` rode the full 10 s grace period and SIGKILLed on every Stop.** `aplay`
  does not react promptly to `SIGTERM` while its stdin is still open and being written
  to, so the bound intended as an unreachable wedged-device backstop had become the
  normal path — leaving the Play button disabled for 10 s after every Stop, or up to
  20 s with an effect. `Playback` now holds the pipeline's sink and closes it *before*
  terminating, handing the reader EOF so it exits on its own. Measured after the fix:
  **0.21 s** (aplay only) and **0.01 s** (ffmpeg into aplay). `wait()` is unaffected
  and stays unbounded.
- The empty-state "no voices installed" screen builds its download command from
  `sys.executable` rather than a hardcoded `.venv/bin/python`, so it works when SynTalk
  is launched from the GNOME overview, where the working directory is `$HOME`.
- `VERSION` restored to ending with a trailing newline.

### Changed

- `synthesize()` and `play()` remain for the Save-to-WAV path and for callers holding
  PCM already; both now share pipeline-spawning code with `speak()`.

### Known limitation, measured

Streaming granularity is one Piper chunk, and Piper splits only where espeak sees a
sentence boundary — which needs a capital letter after the full stop, or a line break.
Ordinary prose streams as intended. All-lower-case or unpunctuated text is synthesised
as a single chunk and behaves as it did before streaming: silence until ready, and Stop
cannot interrupt it. Measured with `en_US-lessac-high` on ~400 words:

| Text | Chunks | First audio |
|---|---|---|
| Capitalised sentences | 25 | 0.39 s |
| Same sentence repeated, lower case | 1 | 14.8 s |
| Newline-separated lines | 45 | 0.34 s |
| 300 words, no punctuation | 1 | 6.9 s |

This is a property of Piper's sentence splitting, not of SynTalk. Documented rather
than worked around: pre-splitting text ourselves would mis-split abbreviations like
"Dr. Smith" into unnatural pauses. Adding line breaks between sentences fixes it.

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
