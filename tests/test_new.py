import yaml
from click.testing import CliRunner

from dreame_voice.cli import main
from dreame_voice.config import load_voice
from dreame_voice.new import render_voice


def test_new_voice_covers_every_id_with_original_text_and_comments(project):
    text = render_voice(project, "say")

    assert "# Returning to the dock to charge." in text
    data = yaml.safe_load(text)
    assert data["engine"] == {"type": "say"}
    assert data["lines"][13] == "Returning to the dock to charge."


def test_sound_ids_point_at_firmware_audio(project):
    data = yaml.safe_load(render_voice(project, "say"))
    assert data["lines"][0] == {"file": "archive/audio/firmware/0.ogg"}


def test_awkward_text_survives_the_round_trip(project):
    (project / "archive" / "sounds.csv").write_text(
        'ID,Filename,Text\n0,0.ogg,Robot startup sound.\n13,13.ogg,"Yes: no # maybe, \'quoted\' ""too"""\n'
    )
    data = yaml.safe_load(render_voice(project, "say"))
    assert data["lines"][13] == "Yes: no # maybe, 'quoted' \"too\""


def test_cli_new_writes_a_loadable_voice(project):
    result = CliRunner().invoke(main, ["--root", str(project), "new", "fresh", "--engine", "fake"])
    assert result.exit_code == 0, result.output
    voice = load_voice(project, "fresh")
    assert [line.id for line in voice.lines] == ["0", "13"]


def test_cli_new_refuses_to_overwrite(project):
    result = CliRunner().invoke(main, ["--root", str(project), "new", "beep", "--engine", "fake"])
    assert result.exit_code != 0
    assert "exists" in result.output
