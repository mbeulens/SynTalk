import shlex
import sys
from pathlib import Path

from syntalk.commandline import play_command, save_command
from syntalk.voices import Voice

# A deliberately non-22050 rate: a hardcoded 22050 in commandline.py would
# make these pass for the wrong reason.
_RATE = 24000


def _voice(num_speakers=1, sample_rate=_RATE):
    return Voice(
        model_path=Path("/models/en_US-lessac-high.onnx"),
        key="en_US-lessac-high",
        display_name="Lessac",
        language_code="en_US",
        language_label="English (United States)",
        sample_rate=sample_rate,
        num_speakers=num_speakers,
        speaker_names=tuple(f"s{i}" for i in range(num_speakers)),
    )


def test_play_command_no_effect_pipes_output_raw_into_aplay():
    cmd = play_command(_voice(), "hello there")

    assert "--output-raw" in cmd
    assert "ffmpeg" not in cmd
    assert cmd.endswith(f"aplay -q -r {_RATE} -f S16_LE -t raw -")
    assert f"-m {shlex.quote('/models/en_US-lessac-high.onnx')}" in cmd


def test_play_command_uses_voice_sample_rate_not_a_hardcoded_default():
    cmd = play_command(_voice(sample_rate=48000), "hi")
    assert "48000" in cmd
    assert str(_RATE) not in cmd


def test_play_command_with_chain_routes_through_ffmpeg_af():
    cmd = play_command(_voice(), "hello", chain="atempo=1.5,highpass=f=200")

    assert "--output-raw" in cmd
    assert f"-ar {_RATE}" in cmd
    assert "-af " + shlex.quote("atempo=1.5,highpass=f=200") in cmd
    assert cmd.endswith("| aplay -q -")


def test_play_command_speaker_flag_present_for_multi_speaker_voice():
    cmd = play_command(_voice(num_speakers=5), "hi", speaker_id=3)
    assert "-s 3" in cmd


def test_play_command_speaker_flag_absent_for_single_speaker_voice():
    # Even if a caller passes a speaker_id by mistake, a single-speaker
    # voice never gets -s: piper would reject it.
    cmd = play_command(_voice(num_speakers=1), "hi", speaker_id=3)
    assert "-s 3" not in cmd


def test_play_command_speaker_flag_absent_when_none():
    cmd = play_command(_voice(num_speakers=5), "hi", speaker_id=None)
    assert "-s" not in shlex.split(cmd)


def test_play_command_quotes_single_quote_and_command_substitution():
    dangerous = "it's $(rm -rf ~) and `whoami`"
    cmd = play_command(_voice(), dangerous)

    assert shlex.quote(dangerous) in cmd
    # The whole command must tokenize back to the exact original text as a
    # single literal argument -- proof a shell would never execute it.
    tokens = shlex.split(cmd)
    assert dangerous in tokens
    assert "$(rm -rf ~)" not in [t for t in tokens if t != dangerous]


def test_save_command_no_effect_uses_piper_f_flag():
    cmd = save_command(_voice(), "hello", "/tmp/out.wav")
    assert cmd.endswith(f"-f {shlex.quote('/tmp/out.wav')}")
    assert "ffmpeg" not in cmd


def test_save_command_with_chain_routes_through_ffmpeg():
    cmd = save_command(_voice(), "hello", "/tmp/out.wav", chain="volume=1.4")
    assert "--output-raw" in cmd
    assert "-y" in cmd
    assert f"-ar {_RATE}" in cmd
    assert "-af " + shlex.quote("volume=1.4") in cmd
    assert cmd.endswith(shlex.quote("/tmp/out.wav"))


def test_save_command_quotes_path_with_spaces():
    cmd = save_command(_voice(), "hi", "/tmp/my file.wav")
    assert shlex.quote("/tmp/my file.wav") in cmd


def test_save_command_speaker_flag_present_only_for_multi_speaker():
    with_speaker = save_command(_voice(num_speakers=3), "hi", "/tmp/o.wav", speaker_id=2)
    without_speaker = save_command(_voice(num_speakers=1), "hi", "/tmp/o.wav", speaker_id=2)
    assert "-s 2" in with_speaker
    assert "-s 2" not in without_speaker


def test_length_scale_reflected_in_both_commands():
    play = play_command(_voice(), "hi", length_scale=1.45)
    save = save_command(_voice(), "hi", "/tmp/o.wav", length_scale=1.45)
    assert "--length-scale 1.45" in play
    assert "--length-scale 1.45" in save


def test_piper_token_is_an_absolute_path_when_installed_beside_the_interpreter(
    tmp_path, monkeypatch
):
    """A bare `piper` is not on PATH for venv installs, so the reproduced
    command must name the console script next to sys.executable."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "piper").touch()
    monkeypatch.setattr(sys, "executable", str(fake_bin / "python"))

    cmd = play_command(_voice(), "hi")

    assert shlex.quote(str(fake_bin / "piper")) in cmd
    assert not cmd.split("| ")[1].startswith("piper ")


def test_piper_token_falls_back_to_bare_name_when_not_beside_the_interpreter(
    tmp_path, monkeypatch
):
    """System-wide installs do have piper on PATH; do not invent a path."""
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "python"))

    cmd = play_command(_voice(), "hi")

    assert "| piper -m " in cmd
