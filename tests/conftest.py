from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


def make_wav(path: Path, seconds: float = 0.2, rate: int = 22050, channels: int = 1) -> None:
    t = np.arange(int(seconds * rate)) / rate
    tone = 0.3 * np.sin(2 * np.pi * 440 * t)
    sf.write(path, np.column_stack([tone] * channels), rate, subtype="PCM_16")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal project root with one dialog script and one voice."""
    (tmp_path / "dialog" / "test").mkdir(parents=True)
    (tmp_path / "dialog" / "test" / "sounds.csv").write_text(
        'ID,Filename,Text\n0,0.ogg,Robot startup sound.\n13,13.ogg,"I\'m done. Going back home to charge."\n'
    )
    (tmp_path / "voices").mkdir()
    (tmp_path / "voices" / "beep.yaml").write_text(
        "dialog: test\nengine:\n  type: fake\n"
    )
    return tmp_path
