# SynTalk — Handoff

**Date:** 2026-08-05
**Machine:** legion-ubunti (Ubuntu 24.04, Python 3.12.3, NVIDIA RTX 4070)
**Goal for the next agent:** turn the working shell prototypes described below into a small, clean Python script/package.

---

## 1. What already exists and works

A local neural TTS stack is installed and verified end-to-end. Audio plays out of the
speakers correctly. Nothing here needs to be re-installed or re-tested — treat it as
the working baseline.

### Installed components

| Path | What it is |
|---|---|
| `~/.local/share/piper-venv/` | Isolated venv: **piper-tts 1.6.0**, onnxruntime 1.28.0, numpy 2.5.1. Created with `uv`. No system Python packages were touched. |
| `~/.local/share/piper-venv/bin/piper` | Piper CLI entry point |
| `~/.local/share/piper-voices/` | Downloaded ONNX voice models + their `.json` configs (~600 MB) |
| `~/.local/bin/say` | Bash prototype — plain TTS wrapper |
| `~/.local/bin/sayfx` | Bash prototype — TTS + ffmpeg character effects |

`~/.local/bin` is already on `PATH` via `~/.bashrc`.

### System tools relied on

- `ffmpeg` — installed at `/usr/bin/ffmpeg` (used for all audio effects)
- `aplay` (alsa-utils) — used for playback of raw/wav streams
- `sox` is **NOT** installed. All effects use ffmpeg filters instead.
- `speech-dispatcher` + `espeak-ng` are also installed system-wide, but rejected —
  the robotic quality was unacceptable. Do not build on `spd-say`.

### Installed voices

```
en_GB-alan-medium                      single speaker
en_GB-cori-high                        single speaker
en_GB-northern_english_male-medium     single speaker
en_GB-vctk-medium                      109 speakers  (-n 0..108)
en_US-l2arctic-medium                   24 speakers  (-n 0..23)   non-native accents
en_US-lessac-high                      single speaker   <- default
nl_BE-nathalie-medium                  single speaker   Flemish female
nl_NL-pim-medium                       single speaker   Dutch male
```

All installed voices are **22050 Hz, 16-bit mono**. Do not hardcode this — read
`audio.sample_rate` from the voice's `.json` config, since other Piper voices differ.

The full Piper catalogue is **171 voices across 53 languages**. All are ordinary
human-reading voices; there are no character/novelty voices in the catalogue.

---

## 2. CLI examples — everything currently supported

### 2.1 `say` — plain TTS

```bash
say "whatever you want to hear"           # speak arguments
echo "text" | say                         # speak stdin
cat report.md | say                       # read a file aloud

say -v nl_NL-pim-medium "hallo daar"      # pick a voice
say -v en_GB-cori-high "British female"

say -s 1.15 "slightly slower"             # length-scale: >1 slower, <1 faster
say -s 0.85 "slightly faster"

say -n 42 -v en_GB-vctk-medium "speaker 42 of 109"     # multi-speaker models
say -n 3  -v en_US-l2arctic-medium "accented English"

say -o out.wav "save to a file instead of playing"
say -l                                    # list voices + speaker counts
say -h                                    # usage
```

Default voice is `en_US-lessac-high`, overridable with the `SAY_VOICE` env var.

### 2.2 `sayfx` — character effects

```bash
sayfx yoda "you must learn patience"
sayfx robot "resistance is futile"
sayfx demon "your soul is mine"
sayfx giant "who dares disturb my slumber"
sayfx ghost "I have been waiting for you"
sayfx chipmunk "hello hello hello"
sayfx tiny "I am very small"
sayfx radio "breaking news at eleven"
sayfx announcer "in a world, where one man"
sayfx drunk "I am perfectly fine to drive"

sayfx -l                                  # list presets
sayfx -o out.wav demon "saved to file"
echo "piped text works too" | sayfx robot
```

The `yoda` preset additionally rewrites the sentence into Yoda word order
(second half of the clause moved to the front, `, yes` appended) *before* synthesis.

### 2.3 Raw Piper CLI (what the wrappers call underneath)

```bash
PIPER=~/.local/share/piper-venv/bin/piper
V=~/.local/share/piper-voices

# to a WAV file
echo "hello world" | $PIPER -m $V/en_US-lessac-high.onnx -f out.wav

# streamed straight to the speakers (raw s16le, rate from the voice config)
echo "hello world" | $PIPER -m $V/en_US-lessac-high.onnx --output-raw \
  | aplay -q -r 22050 -f S16_LE -t raw -

# knobs
$PIPER -m MODEL --length-scale 1.2      # phoneme duration -> speed
$PIPER -m MODEL --noise-scale 0.667     # variability of the generated audio
$PIPER -m MODEL --noise-w-scale 0.8     # variability of phoneme durations
$PIPER -m MODEL --sentence-silence 0.4  # seconds of pause between sentences
$PIPER -m MODEL --volume 1.0
$PIPER -m MODEL -s 42                   # speaker id (multi-speaker models)
$PIPER -m MODEL --cuda                  # GPU inference (needs onnxruntime-gpu)
$PIPER -m MODEL -i input.txt -d outdir/ --output-dir-naming timestamp
```

### 2.4 Downloading more voices

```bash
PY=~/.local/share/piper-venv/bin/python

$PY -m piper.download_voices                                   # list all 171
$PY -m piper.download_voices --data-dir ~/.local/share/piper-voices en_US-ryan-high
```

Medium voices are ~61 MB, high voices ~109 MB, each with a small `.json` sidecar.

---

## 3. The effect presets

Each preset is `piper-voice | length-scale | ffmpeg filter chain`.
`@SR@` is substituted with the voice's sample rate at runtime.

| Preset | Voice | Speed | ffmpeg filter chain |
|---|---|---|---|
| `yoda` | en_GB-alan-medium | 1.45 | `asetrate=@SR@*1.22,aresample=@SR@,atempo=0.82,vibrato=f=6:d=0.35,aecho=0.8:0.7:22:0.18` |
| `robot` | en_US-lessac-high | 1.0 | `asetrate=@SR@*0.92,aresample=@SR@,atempo=1.09,flanger=delay=6:depth=4:speed=1.2,aecho=0.9:0.85:12:0.5,acompressor` |
| `chipmunk` | en_US-lessac-high | 0.92 | `asetrate=@SR@*1.55,aresample=@SR@,atempo=0.68` |
| `demon` | en_US-lessac-high | 1.25 | `asetrate=@SR@*0.62,aresample=@SR@,atempo=1.55,aecho=0.9:0.9:180:0.4,acompressor` |
| `giant` | en_GB-alan-medium | 1.35 | `asetrate=@SR@*0.74,aresample=@SR@,atempo=1.3,aecho=0.9:0.88:320:0.45` |
| `ghost` | en_GB-cori-high | 1.3 | `asetrate=@SR@*0.96,aresample=@SR@,atempo=1.04,chorus=0.6:0.9:55:0.4:0.25:2,aecho=0.9:0.9:480:0.6,highpass=f=180` |
| `radio` | en_US-lessac-high | 1.0 | `highpass=f=500,lowpass=f=2600,acrusher=bits=10:mode=log,volume=1.4` |
| `drunk` | en_US-lessac-high | 1.32 | `vibrato=f=2.4:d=0.7,atempo=0.95,aecho=0.7:0.6:60:0.2` |
| `announcer` | en_US-lessac-high | 1.08 | `asetrate=@SR@*0.9,aresample=@SR@,atempo=1.11,aecho=0.85:0.75:240:0.3,acompressor,volume=1.3` |
| `tiny` | en_GB-cori-high | 0.95 | `asetrate=@SR@*1.32,aresample=@SR@,atempo=0.8,highpass=f=400` |

**Pitch-shift idiom:** `asetrate=SR*K,aresample=SR,atempo=1/K` shifts pitch by factor
`K` while keeping the original duration. `atempo` only accepts 0.5–2.0 per instance —
chain multiple `atempo` filters for larger changes.

---

## 4. Piper's Python API (verified against 1.6.0 on this machine)

Prefer this over shelling out to the CLI — it avoids a process spawn and a model
reload per utterance, which matters a lot if the script speaks repeatedly.

```python
from piper import PiperVoice, SynthesisConfig

voice = PiperVoice.load(
    "/home/beuner/.local/share/piper-voices/en_US-lessac-high.onnx",
    config_path=None,      # defaults to <model>.json
    use_cuda=False,        # True needs onnxruntime-gpu, not currently installed
)

cfg = SynthesisConfig(
    speaker_id=None,       # int for multi-speaker models
    length_scale=1.0,      # >1 slower
    noise_scale=None,
    noise_w_scale=None,
    normalize_audio=True,
    volume=1.0,
)

# streaming: yields AudioChunk objects
for chunk in voice.synthesize("hello world", syn_config=cfg):
    chunk.sample_rate        # int
    chunk.sample_width       # 2 (bytes)
    chunk.sample_channels    # 1
    chunk.audio_int16_bytes  # bytes, ready to write to a stream
    chunk.audio_int16_array  # numpy array
    chunk.audio_float_array  # numpy array

# or straight to a wave file
import wave
with wave.open("out.wav", "wb") as wf:
    voice.synthesize_wav("hello world", wf, syn_config=cfg)
```

Voice metadata lives in the `.json` sidecar next to each `.onnx`:

```python
import json
meta = json.load(open(model_path + ".json"))
meta["audio"]["sample_rate"]   # 22050
meta["num_speakers"]           # 1, or 109 for vctk
meta["speaker_id_map"]         # {"p239": 0, "p236": 1, ...}
meta["language"]["code"]       # "en_US"
```

---

## 5. What to build

A small Python script/package replacing both bash prototypes. Suggested shape:

- **Single entry point** with subcommands or a `--fx` flag, rather than two scripts.
- **Load the model once**, then loop — support reading stdin line by line and
  speaking each line as it arrives, so it can be used as a pipe sink.
- **Playback:** either pipe `audio_int16_bytes` to `aplay` via `subprocess`, or use
  `sounddevice`/`simpleaudio` if you'd rather not shell out. `aplay` is proven to work.
- **Effects:** keep them declarative (a dict of presets, as above) so new ones are a
  one-line addition. Applying them via `ffmpeg` on a temp WAV is proven; doing it in
  numpy would remove the ffmpeg dependency but is a bigger job — ffmpeg is fine.
- **Voice discovery:** scan `~/.local/share/piper-voices/*.onnx`, read each `.json`
  for speaker count and sample rate. Don't hardcode the voice list.
- **Config:** honour `SAY_VOICE`; consider a small TOML/JSON config file for the
  default voice, speed, and custom presets.
- **Keep `-o/--output`** for writing WAV instead of playing.

### Constraints and gotchas

- Sample rate must come from the voice config, not a constant.
- `atempo` is limited to 0.5–2.0 per filter instance; chain them.
- Multi-speaker models require a valid `speaker_id` in range or synthesis errors.
- Empty/whitespace-only input should exit cleanly, not crash or emit silence forever.
- The venv is separate from any project venv. Either run the script with
  `~/.local/share/piper-venv/bin/python`, or create the project venv with
  `uv venv && uv pip install piper-tts` and let it have its own copy.
- Everything is offline after the model download. Do not add network calls at runtime.

### Explicitly out of scope

Voice cloning (real Yoda, celebrity voices) was discussed and **deferred**. It needs a
different model class — Chatterbox (MIT), XTTS-v2 (non-commercial), or F5-TTS — plus a
~3 GB PyTorch/CUDA install and reference audio clips. Not part of this task.

---

## 6. Reference: current bash prototypes

Read these before writing the Python version — they encode the working behaviour,
including the exact argument handling, defaults, and error paths to reproduce:

- `reference/say` — plain TTS wrapper
- `reference/sayfx` — TTS + ffmpeg character effects

These are verbatim copies (2026-08-05) of the live scripts at `~/.local/bin/say` and
`~/.local/bin/sayfx`. They are **reference only — do not edit them**; the copies here
will drift from the originals. The Python version replaces both.
