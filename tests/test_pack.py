import hashlib
import tarfile

from dreame_voice.pack import build_pack


def test_pack_has_flat_ogg_entries_and_md5(tmp_path):
    audio = tmp_path / "audio"
    audio.mkdir()
    for name in ("0.ogg", "13.ogg"):
        (audio / name).write_bytes(name.encode())
    (audio / "stray.wav").write_bytes(b"x")
    pack = tmp_path / "out" / "beep.tar.gz"
    md5 = tmp_path / "out" / "beep.md5"

    digest = build_pack(audio, pack, md5)

    with tarfile.open(pack) as tar:
        members = tar.getmembers()
    assert sorted(m.name for m in members) == ["0.ogg", "13.ogg"]
    assert all(m.uid == 0 and m.gid == 0 and m.mode == 0o644 for m in members)
    assert digest == hashlib.md5(pack.read_bytes()).hexdigest()
    assert md5.read_text() == digest + "\n"


def test_pack_is_reproducible(tmp_path):
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "0.ogg").write_bytes(b"a")
    first = build_pack(audio, tmp_path / "a.tar.gz", tmp_path / "a.md5")
    (audio / "0.ogg").touch()
    second = build_pack(audio, tmp_path / "b.tar.gz", tmp_path / "b.md5")
    assert first == second
