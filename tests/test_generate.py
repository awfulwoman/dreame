import tarfile

import soundfile as sf
from click.testing import CliRunner

from dreame_voice import engines
from dreame_voice.cli import main
from dreame_voice.config import load_voice
from dreame_voice.generate import generate

from .conftest import make_wav


class FakeEngine:
    def __init__(self):
        self.spoken = []

    def synthesize(self, text, wav_path):
        self.spoken.append(text)
        make_wav(wav_path)


def use_fake(monkeypatch, fake=None):
    fake = fake or FakeEngine()
    monkeypatch.setitem(engines.ENGINES, "fake", lambda options, root: fake)
    return fake


def test_speaks_text_lines_copies_file_lines_and_packs_both(project, monkeypatch):
    fake = use_fake(monkeypatch)
    voice = load_voice(project, "beep")

    generate(voice)

    assert fake.spoken == ["I'm done. Going back home to charge."]
    assert sorted(p.name for p in voice.audio_dir.iterdir()) == ["0.ogg", "13.ogg"]
    info = sf.info(voice.audio_dir / "0.ogg")
    assert (info.format, info.subtype, info.samplerate, info.channels) == ("OGG", "VORBIS", 16000, 1)
    with tarfile.open(voice.pack_path) as tar:
        assert sorted(tar.getnames()) == ["0.ogg", "13.ogg"]
    assert voice.md5_path.exists()


def test_only_some_ids_still_packs_everything(project, monkeypatch):
    fake = use_fake(monkeypatch)
    voice = load_voice(project, "beep")
    generate(voice)
    fake.spoken.clear()

    generate(voice, only={"13"})

    assert fake.spoken == ["I'm done. Going back home to charge."]
    with tarfile.open(voice.pack_path) as tar:
        assert sorted(tar.getnames()) == ["0.ogg", "13.ogg"]


def test_stale_files_are_removed(project, monkeypatch):
    use_fake(monkeypatch)
    voice = load_voice(project, "beep")
    voice.audio_dir.mkdir(parents=True)
    (voice.audio_dir / "999.ogg").write_bytes(b"old")

    generate(voice)

    assert not (voice.audio_dir / "999.ogg").exists()


def test_engine_not_loaded_when_no_text_lines_are_generated(project, monkeypatch):
    def explode(options, root):
        raise AssertionError("engine loaded")

    monkeypatch.setitem(engines.ENGINES, "fake", explode)
    voice = load_voice(project, "beep")
    voice.audio_dir.mkdir(parents=True)
    (voice.audio_dir / "13.ogg").write_bytes(b"kept")

    generate(voice, only={"0"})


def test_cli_generate(project, monkeypatch):
    use_fake(monkeypatch)
    result = CliRunner().invoke(main, ["--root", str(project), "generate", "beep"])
    assert result.exit_code == 0, result.output
    assert "BEEP" in result.output
    assert (project / "build" / "beep.tar.gz").exists()


def test_cli_list(project):
    result = CliRunner().invoke(main, ["--root", str(project), "list"])
    assert result.exit_code == 0, result.output
    assert "beep" in result.output and "fake" in result.output
