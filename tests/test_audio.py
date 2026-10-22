import soundfile as sf

from dreame_voice.audio import to_ogg

from .conftest import make_wav


def test_converts_to_mono_16k_vorbis_like_the_manufacturer_files(tmp_path):
    wav = tmp_path / "in.wav"
    ogg = tmp_path / "out.ogg"
    make_wav(wav, seconds=0.5, rate=44100, channels=2)

    to_ogg(wav, ogg)

    info = sf.info(ogg)
    assert (info.format, info.subtype, info.samplerate, info.channels) == ("OGG", "VORBIS", 16000, 1)
    assert abs(info.duration - 0.5) < 0.01


def test_reads_manufacturer_file_format(tmp_path):
    # Sanity check that libsndfile reads the robot's own files
    from pathlib import Path

    original = Path(__file__).parent.parent / "archive" / "audio" / "xiaomi" / "7.ogg"
    info = sf.info(original)
    assert (info.samplerate, info.channels) == (16000, 1)
