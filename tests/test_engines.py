import shutil
import sys
import wave

import pytest

from dreame_voice.engines import EngineError, get_engine


def test_unknown_engine_raises():
    with pytest.raises(EngineError, match="nope"):
        get_engine("nope", {}, root=None)


def test_unknown_option_raises():
    with pytest.raises(EngineError, match="colour"):
        get_engine("say", {"voice": "Moira", "colour": "blue"}, root=None)


@pytest.mark.skipif(sys.platform != "darwin" or shutil.which("say") is None, reason="macOS say only")
def test_say_writes_wav_and_handles_shell_characters(tmp_path):
    wav = tmp_path / "out.wav"
    engine = get_engine("say", {"voice": "Moira"}, root=tmp_path)
    engine.synthesize("I'm done; (going) home & \"charging\".", wav)
    with wave.open(str(wav)) as w:
        assert w.getnframes() > 0


def test_piper_requires_model():
    with pytest.raises(EngineError, match="model"):
        get_engine("piper", {}, root=None)


def test_xtts_requires_speaker_wav():
    with pytest.raises(EngineError, match="speaker_wav"):
        get_engine("xtts", {}, root=None)
