from pathlib import Path

import pytest

from dreame_voice.archive import load_reference


def test_reference_maps_ids_to_original_text_in_file_order(project):
    assert load_reference(project) == {
        "0": "Robot startup sound.",
        "13": "Returning to the dock to charge.",
    }


def test_missing_archive_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="archive/sounds.csv"):
        load_reference(tmp_path)


def test_real_archive_parses():
    reference = load_reference(Path(__file__).parent.parent)
    assert len(reference) > 100
    assert all(k.isdigit() and v for k, v in reference.items())
