import pytest

from datetime import date, timedelta

from dreame_voice.config import ConfigError, Line, load_voice, voice_names

from .conftest import BEEP_YAML


def write(project, body):
    (project / "voices" / "beep.yaml").write_text(body)


def test_loads_engine_and_lines_in_archive_order(project):
    voice = load_voice(project, "beep")
    assert voice.name == "beep"
    assert voice.engine == "fake"
    assert voice.engine_options == {}
    assert voice.lines == [
        Line(id="0", file=project / "archive" / "audio" / "firmware" / "0.ogg"),
        Line(id="13", text="I'm done. Going back home to charge."),
    ]


def test_language_id_defaults_to_uppercase_name(project):
    assert load_voice(project, "beep").language_id == "BEEP"


def test_language_id_can_be_set(project):
    write(project, "language_id: BP\n" + BEEP_YAML)
    assert load_voice(project, "beep").language_id == "BP"


@pytest.mark.parametrize("language_id", ["EN", "ZH", "en"])
def test_builtin_language_ids_are_rejected(project, language_id):
    # The firmware plays /audio/EN and /audio/ZH for these, never /data/personalized_voice
    write(project, f"language_id: {language_id}\n" + BEEP_YAML)
    with pytest.raises(ConfigError, match="built-in"):
        load_voice(project, "beep")


def test_engine_options_are_everything_except_type(project):
    write(project, BEEP_YAML.replace("  type: fake\n", "  type: say\n  voice: Moira\n  rate: 180\n"))
    voice = load_voice(project, "beep")
    assert voice.engine == "say"
    assert voice.engine_options == {"voice": "Moira", "rate": 180}


def test_paths_follow_naming_convention(project):
    voice = load_voice(project, "beep")
    assert voice.audio_dir == project / "build" / "beep"
    assert voice.pack_path == project / "build" / "beep.tar.gz"
    assert voice.md5_path == project / "build" / "beep.md5"


def test_missing_ids_are_rejected(project):
    write(project, "engine:\n  type: fake\nlines:\n  13: Hello.\n")
    with pytest.raises(ConfigError, match="missing line.*\\b0\\b"):
        load_voice(project, "beep")


def test_unknown_ids_are_rejected(project):
    write(project, BEEP_YAML + "  999: Not a real prompt.\n")
    with pytest.raises(ConfigError, match="unknown.*999"):
        load_voice(project, "beep")


def test_missing_sound_file_is_rejected(project):
    write(project, BEEP_YAML.replace("firmware/0.ogg", "firmware/nope.ogg"))
    with pytest.raises(ConfigError, match="nope.ogg"):
        load_voice(project, "beep")


@pytest.mark.parametrize("value", ["", "{text: hi}", "{file: a.ogg, extra: 1}", "[]", "[a, '']"])
def test_bad_line_values_are_rejected(project, value):
    write(project, BEEP_YAML.replace("I'm done. Going back home to charge.", value))
    with pytest.raises(ConfigError, match="13"):
        load_voice(project, "beep")


@pytest.mark.parametrize("body,message", [
    ("lines:\n  0: a\n  13: b\n", "engine"),
    ("engine:\n  voice: x\nlines:\n  0: a\n  13: b\n", "type"),
    ("engine:\n  type: fake\n", "lines"),
])
def test_missing_fields_raise(project, body, message):
    write(project, body)
    with pytest.raises(ConfigError, match=message):
        load_voice(project, "beep")


def test_unknown_voice_raises(project):
    with pytest.raises(ConfigError, match="voices/nope.yaml"):
        load_voice(project, "nope")


def test_voice_names_lists_yaml_files(project):
    (project / "voices" / "another.yaml").write_text(BEEP_YAML)
    assert voice_names(project) == ["another", "beep"]


VARIANTS_YAML = BEEP_YAML.replace(
    "  13: I'm done. Going back home to charge.\n",
    "  13:\n    - Going home.\n    - Back to the dock.\n    - Off to charge.\n",
)


def texts(project, days):
    start = date(2026, 1, 1)
    return [load_voice(project, "beep", on=start + timedelta(days=d)).lines[1].text for d in days]


def test_a_line_can_have_variants_and_one_is_picked(project):
    write(project, VARIANTS_YAML)
    (text,) = texts(project, [0])
    assert text in {"Going home.", "Back to the dock.", "Off to charge."}


def test_variant_holds_for_rotate_days_then_changes(project):
    write(project, "rotate_days: 3\n" + VARIANTS_YAML)
    start = date(2026, 1, 1)
    by_period = {}
    for d, text in zip(range(30), texts(project, range(30))):
        by_period.setdefault((start + timedelta(days=d)).toordinal() // 3, set()).add(text)
    assert all(len(picked) == 1 for picked in by_period.values())
    assert set().union(*by_period.values()) == {"Going home.", "Back to the dock.", "Off to charge."}


def test_consecutive_periods_never_repeat_a_variant(project):
    write(project, "rotate_days: 1\n" + VARIANTS_YAML)
    picks = texts(project, range(20))
    assert all(a != b for a, b in zip(picks, picks[1:]))


def test_rotate_days_defaults_to_3(project):
    write(project, VARIANTS_YAML)
    assert load_voice(project, "beep").rotate_days == 3


@pytest.mark.parametrize("value", ["0", "-1", "soon"])
def test_bad_rotate_days_are_rejected(project, value):
    write(project, f"rotate_days: {value}\n" + VARIANTS_YAML)
    with pytest.raises(ConfigError, match="rotate_days"):
        load_voice(project, "beep")


def test_variants_can_mix_text_and_files(project):
    write(project, VARIANTS_YAML.replace("    - Off to charge.\n", "    - file: archive/audio/firmware/0.ogg\n"))
    lines = {load_voice(project, "beep", on=date(2026, 1, 1) + timedelta(days=d)).lines[1]
             for d in range(0, 9, 3)}
    assert Line(id="13", file=project / "archive" / "audio" / "firmware" / "0.ogg") in lines


def test_variant_counts_are_reported(project):
    write(project, VARIANTS_YAML)
    assert load_voice(project, "beep").variant_counts == {"0": 1, "13": 3}


def test_next_change_is_the_first_day_of_the_next_period(project):
    write(project, "rotate_days: 3\n" + VARIANTS_YAML)
    day = date(2026, 1, 1)
    voice = load_voice(project, "beep", on=day)
    nxt = voice.next_change
    assert day < nxt <= day + timedelta(days=3)
    assert load_voice(project, "beep", on=nxt).lines != voice.lines
    assert load_voice(project, "beep", on=nxt - timedelta(days=1)).lines == voice.lines


def test_next_change_is_none_without_variants(project):
    assert load_voice(project, "beep").next_change is None
