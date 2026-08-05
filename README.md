# SynTalk

**Version:** 0.1.8

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

- Pick a voice in the sidebar. Multi-speaker voices show a speaker selector, plus a
  **next speaker** button that advances to the next speaker (wrapping past the last)
  and immediately plays the current text — handy for auditioning VCTK's 109 speakers.
- Type into the text field. **Play**, or `Ctrl+Return`.
- **Effect** applies a character preset's filter chain to whatever voice is currently
  selected, and sets the speed slider to match. It never changes the selected voice —
  change either afterwards if you like.
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
uv venv --system-site-packages --python 3.12
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
