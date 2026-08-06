# SynTalk

**Version:** 0.2.0

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

- Synthesis is not streamed. The whole utterance is generated before playback starts,
  so a page of text means roughly 30 seconds of silence first, and playback cannot be
  cancelled until it begins. Budget about 2.65 MB of memory per minute of audio.
- No CLI yet. `voices.py`, `effects.py`, `engine.py` and `commandline.py` are
  deliberately GTK-free so adding one stays cheap.
- Voice cloning is out of scope — it needs a different model class entirely.
