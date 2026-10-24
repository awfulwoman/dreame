import gzip
import hashlib
import io
import os
import tarfile
from pathlib import Path


def _id_key(path: Path):
    return (0, int(path.stem)) if path.stem.isdigit() else (1, path.stem)


def build_pack(audio_dir: Path, pack_path: Path, md5_path: Path) -> str:
    """Tar every <id>.ogg in audio_dir at the archive root, as the robot expects.

    Ownership and timestamps are fixed so the same audio always gives the same MD5.
    Returns the MD5 hex digest.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for ogg in sorted(audio_dir.glob("*.ogg"), key=_id_key):
            info = tarfile.TarInfo(ogg.name)
            info.size = ogg.stat().st_size
            info.mode = 0o644
            info.mtime = 0
            with ogg.open("rb") as f:
                tar.addfile(info, f)

    pack_path.parent.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(buf.getvalue(), mtime=0)
    # Write then rename: the service may be serving the old pack meanwhile
    tmp = pack_path.with_name(pack_path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, pack_path)
    digest = hashlib.md5(data).hexdigest()
    md5_path.write_text(digest + "\n")
    return digest
