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
