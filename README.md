# SynTalk

**Version:** 0.3.0

Local neural text-to-speech with a GTK 4 interface. Pick a voice, type, press play.
Everything runs offline on your own machine.

Built on [Piper](https://github.com/OHF-Voice/piper1-gpl) for synthesis and `ffmpeg`
for the character effects. See [CHANGELOG.md](CHANGELOG.md) for what changed.

```
┌─ Voices ──────────┬─ SynTalk ──────────────────── [Save WAV] ─┐
│ ● Lessac    US    │  Speaker  [ 42 ]   (multi-speaker only)   │
│   Alan      GB    │  ┌────────────────────────────────────┐   │
│   Cori      GB    │  │  type anything here…               │   │
│   VCTK      GB ¹⁰⁹│  └────────────────────────────────────┘   │
│   L2Arctic  US ²⁴ │  Effect [None ▾] Length ─●─ [⏭][▶ Play]  │
│   Nathalie  BE    │  ▸ Log                                    │
└───────────────────┴───────────────────────────────────────────┘
```

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

- Pick a voice in the sidebar. Multi-speaker voices show a speaker selector, plus a
  **next speaker** button that advances to the next speaker (wrapping past the last)
  and immediately plays the current text — handy for auditioning VCTK's 109 speakers.
- Type into the text field. **Play**, or `Ctrl+Return`.
- **Effect** applies a character preset's filter chain to whatever voice is currently
  selected, and sets the speed slider to match. It never changes the selected voice —
  change either afterwards if you like.
- The save button in the header writes the current text to a WAV file.
- **Log** at the bottom is a collapsible session log (collapsed by default). Every
  play, next-speaker play and save appends a timestamped entry recording the text
  spoken and the equivalent shell command — genuinely copy-pasteable, quoting handled
  for you — so you can reproduce what SynTalk just did from a terminal. Failures are
  logged too. **Copy** puts the whole log on the clipboard; **Clear** empties it. The
  log is never truncated automatically — only Clear does that.

## Downloading more voices

```bash
.venv/bin/python -m piper.download_voices \
  --data-dir ~/.local/share/piper-voices en_US-ryan-high
```

SynTalk discovers whatever is in that directory at launch. 171 voices across 53
languages are available.

## Development

```bash
uv venv --system-site-packages --python 3.12 --clear
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
Minor and major bumps are merged from `dev` into `master` and recorded in
[CHANGELOG.md](CHANGELOG.md).

The version is kept in step across four files — `VERSION`, this README's
`**Version:**` line, `pyproject.toml`, and `src/syntalk/__init__.py`.

## Known limitations

- No CLI yet. `voices.py`, `effects.py`, `engine.py` and `commandline.py` are
  deliberately GTK-free so adding one stays cheap.
- Voice cloning is out of scope — it needs a different model class entirely.
- Saving to WAV (`Engine.save_wav`) still buffers the whole utterance before writing —
  nothing is waiting to hear a file being written, so this is unaffected by streaming
  playback. Only the Play path streams.
- **Streaming granularity is one sentence, and Piper decides where sentences are.**
  Normally punctuated prose starts playing in about a third of a second no matter how
  long it is, and Stop interrupts within a sentence. But Piper only splits where espeak
  sees a sentence boundary — which needs a capital letter after the full stop, or a line
  break. Text that is all lower case, or one long unpunctuated run, is synthesised as a
  single chunk, so it behaves as it did before streaming: silence until it is ready, and
  Stop cannot interrupt it. Measured on this machine with `en_US-lessac-high`:

  | Text (~400 words) | Chunks | First audio |
  |---|---|---|
  | Capitalised sentences | 25 | 0.39 s |
  | Same sentence repeated, lower case | 1 | 14.8 s |
  | Newline-separated lines | 45 | 0.34 s |
  | 300 words, no punctuation | 1 | 6.9 s |

  If you paste text that starts slowly, adding line breaks between sentences fixes it.
