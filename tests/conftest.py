from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


def _tone(seconds: float, rate: int, channels: int):
    t = np.arange(int(seconds * rate)) / rate
    return np.column_stack([0.3 * np.sin(2 * np.pi * 440 * t)] * channels)


def make_wav(path: Path, seconds: float = 0.2, rate: int = 22050, channels: int = 1) -> None:
    sf.write(path, _tone(seconds, rate, channels), rate, subtype="PCM_16")


def make_ogg(path: Path, seconds: float = 0.2, rate: int = 16000) -> None:
    sf.write(path, _tone(seconds, rate, 1), rate, format="OGG", subtype="VORBIS")


BEEP_YAML = """\
engine:
  type: fake
lines:
  0:
    file: archive/audio/firmware/0.ogg
  13: I'm done. Going back home to charge.
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal project root: an archive with two IDs and one voice covering both."""
    (tmp_path / "archive" / "audio" / "firmware").mkdir(parents=True)
    (tmp_path / "archive" / "sounds.csv").write_text(
        "ID,Filename,Text\n0,0.ogg,Robot startup sound.\n13,13.ogg,Returning to the dock to charge.\n"
    )
    make_ogg(tmp_path / "archive" / "audio" / "firmware" / "0.ogg")
    (tmp_path / "voices").mkdir()
    (tmp_path / "voices" / "beep.yaml").write_text(BEEP_YAML)
    return tmp_path
