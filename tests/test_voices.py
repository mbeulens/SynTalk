import json

from syntalk.voices import discover, find


def test_discovers_each_installed_model(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")
    write_voice(voices_dir, "nl_NL-pim-medium", code="nl_NL",
                name_english="Dutch", country_english="Netherlands")

    voices = discover(voices_dir)

    # Sorted by language label: "Dutch (Netherlands)" < "English (United States)".
    assert [v.key for v in voices] == ["nl_NL-pim-medium", "en_US-lessac-high"]


def test_parses_metadata(voices_dir, write_voice):
    write_voice(voices_dir, "en_GB-vctk-medium", sample_rate=16000,
                num_speakers=3, speaker_id_map={"p239": 0, "p236": 1, "p264": 2},
                code="en_GB", name_english="English",
                country_english="Great Britain")

    voice = discover(voices_dir)[0]

    assert voice.sample_rate == 16000
    assert voice.num_speakers == 3
    assert voice.is_multi_speaker is True
    assert voice.speaker_names == ("p239", "p236", "p264")
    assert voice.language_code == "en_GB"
    assert voice.language_label == "English (Great Britain)"


def test_single_speaker_voice_is_not_multi_speaker(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")

    voice = discover(voices_dir)[0]

    assert voice.num_speakers == 1
    assert voice.is_multi_speaker is False
    assert voice.speaker_names == ()


def test_display_name_derivation(voices_dir, write_voice):
    for key in [
        "en_US-lessac-high",
        "en_GB-northern_english_male-medium",
        "en_GB-vctk-medium",
        "en_US-l2arctic-medium",
    ]:
        write_voice(voices_dir, key)

    names = {v.key: v.display_name for v in discover(voices_dir)}

    assert names["en_US-lessac-high"] == "Lessac"
    assert names["en_GB-northern_english_male-medium"] == "Northern English Male"
    assert names["en_GB-vctk-medium"] == "VCTK"
    assert names["en_US-l2arctic-medium"] == "L2Arctic"


def test_malformed_sidecar_is_skipped_not_fatal(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")
    (voices_dir / "broken-medium.onnx").write_bytes(b"")
    (voices_dir / "broken-medium.onnx.json").write_text("{ not json")

    voices = discover(voices_dir)

    assert [v.key for v in voices] == ["en_US-lessac-high"]


def test_missing_sidecar_is_skipped(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")
    (voices_dir / "orphan-medium.onnx").write_bytes(b"")

    assert [v.key for v in discover(voices_dir)] == ["en_US-lessac-high"]


def test_sorted_by_language_then_name(voices_dir, write_voice):
    write_voice(voices_dir, "nl_NL-pim-medium", code="nl_NL",
                name_english="Dutch", country_english="Netherlands")
    write_voice(voices_dir, "en_US-lessac-high")
    write_voice(voices_dir, "en_GB-alan-medium", code="en_GB",
                name_english="English", country_english="Great Britain")

    labels = [(v.language_label, v.display_name) for v in discover(voices_dir)]

    assert labels == [
        ("Dutch (Netherlands)", "Pim"),
        ("English (Great Britain)", "Alan"),
        ("English (United States)", "Lessac"),
    ]


def test_missing_directory_returns_empty(tmp_path):
    assert discover(tmp_path / "nope") == []


def test_find_hit_and_miss(voices_dir, write_voice):
    write_voice(voices_dir, "en_US-lessac-high")
    voices = discover(voices_dir)

    assert find("en_US-lessac-high", voices).key == "en_US-lessac-high"
    assert find("does-not-exist", voices) is None


def test_language_label_falls_back_to_code(voices_dir, write_voice):
    write_voice(voices_dir, "xx_YY-mystery-medium")
    path = voices_dir / "xx_YY-mystery-medium.onnx.json"
    meta = json.loads(path.read_text())
    meta["language"] = {"code": "xx_YY"}
    path.write_text(json.dumps(meta))

    assert discover(voices_dir)[0].language_label == "xx_YY"
