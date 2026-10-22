import pytest

from dreame_voice.config import ConfigError, load_voice, voice_names


def test_name_comes_from_filename(project):
    voice = load_voice(project, "beep")
    assert voice.name == "beep"
    assert voice.dialog == "test"
    assert voice.engine == "fake"
    assert voice.engine_options == {}


def test_language_id_defaults_to_uppercase_name(project):
    assert load_voice(project, "beep").language_id == "BEEP"


def test_language_id_can_be_set(project):
    (project / "voices" / "beep.yaml").write_text(
        "dialog: test\nlanguage_id: BP\nengine:\n  type: fake\n"
    )
    assert load_voice(project, "beep").language_id == "BP"


@pytest.mark.parametrize("language_id", ["EN", "ZH", "en"])
def test_builtin_language_ids_are_rejected(project, language_id):
    # The firmware plays /audio/EN and /audio/ZH for these, never /data/personalized_voice
    (project / "voices" / "beep.yaml").write_text(
        f"dialog: test\nlanguage_id: {language_id}\nengine:\n  type: fake\n"
    )
    with pytest.raises(ConfigError, match="built-in"):
        load_voice(project, "beep")


def test_engine_options_are_everything_except_type(project):
    (project / "voices" / "beep.yaml").write_text(
        "dialog: test\nengine:\n  type: say\n  voice: Moira\n  rate: 180\n"
    )
    voice = load_voice(project, "beep")
    assert voice.engine == "say"
    assert voice.engine_options == {"voice": "Moira", "rate": 180}


def test_paths_follow_naming_convention(project):
    voice = load_voice(project, "beep")
    assert voice.audio_dir == project / "audio" / "generated" / "beep"
    assert voice.pack_path == project / "voicepacks" / "beep.tar.gz"
    assert voice.md5_path == project / "voicepacks" / "beep.md5"


@pytest.mark.parametrize("body,message", [
    ("engine:\n  type: fake\n", "dialog"),
    ("dialog: test\n", "engine"),
    ("dialog: test\nengine:\n  voice: x\n", "type"),
])
def test_missing_fields_raise(project, body, message):
    (project / "voices" / "beep.yaml").write_text(body)
    with pytest.raises(ConfigError, match=message):
        load_voice(project, "beep")


def test_unknown_voice_raises(project):
    with pytest.raises(ConfigError, match="voices/nope.yaml"):
        load_voice(project, "nope")


def test_voice_names_lists_yaml_files(project):
    (project / "voices" / "another.yaml").write_text("dialog: test\nengine:\n  type: fake\n")
    assert voice_names(project) == ["another", "beep"]
