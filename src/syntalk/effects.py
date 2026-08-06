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
