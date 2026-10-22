import pytest

from dreame_voice.dialog import Line, load_dialog


def test_loads_lines_with_ids_and_text(project):
    lines = load_dialog(project, "test")
    assert lines == [
        Line(id="0", text="Robot startup sound."),
        Line(id="13", text="I'm done. Going back home to charge."),
    ]


def test_missing_dialog_raises(project):
    with pytest.raises(FileNotFoundError, match="dialog/nope/sounds.csv"):
        load_dialog(project, "nope")


def test_real_dialog_scripts_parse():
    from pathlib import Path

    root = Path(__file__).parent.parent
    for name in ("manufacturer", "custom"):
        lines = load_dialog(root, name)
        assert len(lines) > 100
        assert all(line.id.isdigit() and line.text for line in lines)
