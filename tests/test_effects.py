import pytest

from syntalk.effects import EFFECTS, apply_text_rewrite, filter_chain
from syntalk.voices import discover


def test_all_ten_presets_present():
    assert set(EFFECTS) == {
        "yoda", "robot", "chipmunk", "demon", "giant",
        "ghost", "radio", "drunk", "announcer", "tiny",
    }


def test_sample_rate_substituted():
    chain = filter_chain(EFFECTS["demon"], 16000)

    assert "@SR@" not in chain
    assert "asetrate=16000*0.62" in chain
    assert "aresample=16000" in chain


def test_chain_without_sample_rate_placeholder_is_untouched():
    chain = filter_chain(EFFECTS["radio"], 22050)

    assert chain == EFFECTS["radio"].chain


def test_existing_presets_keep_their_atempo_values():
    # Every shipped preset is already inside ffmpeg's 0.5-2.0 window.
    for effect in EFFECTS.values():
        chain = filter_chain(effect, 22050)
        for part in chain.split(","):
            if part.startswith("atempo="):
                assert 0.5 <= float(part.split("=")[1]) <= 2.0


@pytest.mark.parametrize("value", [3.0, 5.0, 0.3, 0.2, 8.0])
def test_out_of_range_atempo_is_split_into_valid_factors(value):
    from syntalk.effects import Effect

    effect = Effect(name="t", voice_key="x", length_scale=1.0,
                    chain=f"atempo={value}")

    parts = filter_chain(effect, 22050).split(",")
    factors = [float(p.split("=")[1]) for p in parts]

    assert all(0.5 <= f <= 2.0 for f in factors)
    product = 1.0
    for f in factors:
        product *= f
    assert product == pytest.approx(value)


def test_atempo_split_leaves_other_filters_alone():
    from syntalk.effects import Effect

    effect = Effect(name="t", voice_key="x", length_scale=1.0,
                    chain="asetrate=@SR@*4.0,aresample=@SR@,atempo=4.0,volume=1.2")

    chain = filter_chain(effect, 22050)

    assert chain.startswith("asetrate=22050*4.0,aresample=22050,")
    assert chain.endswith(",volume=1.2")
    assert chain.count("atempo=") == 2


def test_yoda_rewrites_word_order():
    result = apply_text_rewrite(EFFECTS["yoda"], "you must learn patience young one")

    assert result == "patience young one, you must learn, yes"


def test_yoda_handles_multiple_sentences():
    result = apply_text_rewrite(EFFECTS["yoda"],
                               "you must learn patience. much to learn you still have")

    assert result == (
        "learn patience, you must, yes. "
        "you still have, much to learn, yes"
    )


def test_yoda_leaves_short_clauses_alone():
    assert apply_text_rewrite(EFFECTS["yoda"], "do or do") == "do or do"


def test_non_rewriting_effects_pass_text_through():
    text = "resistance is futile you will be assimilated"

    assert apply_text_rewrite(EFFECTS["robot"], text) == text


def test_only_yoda_rewrites():
    rewriters = [e.name for e in EFFECTS.values() if e.rewrites_text]

    assert rewriters == ["yoda"]


def test_every_preset_names_an_installed_voice():
    installed = {v.key for v in discover()}
    if not installed:
        pytest.skip("no voices installed on this machine")

    for effect in EFFECTS.values():
        assert effect.voice_key in installed, (
            f"preset {effect.name} wants missing voice {effect.voice_key}"
        )
