import hashlib
import tempfile
from pathlib import Path

from .audio import to_ogg
from .config import Voice
from .engines import get_engine
from .pack import build_pack


def generate(voice: Voice, only: set[str] | None = None, log=print) -> str:
    """Write every line to build/<name>/<id>.ogg, then build the pack.

    Text lines are spoken by the voice's engine; file lines are converted as-is.
    With `only`, regenerate just those IDs and keep the rest. Returns the pack's MD5.
    """
    voice.audio_dir.mkdir(parents=True, exist_ok=True)

    # Drop files for IDs the voice no longer has, so they don't end up in the pack
    ids = {line.id for line in voice.lines}
    for stale in voice.audio_dir.glob("*.ogg"):
        if stale.stem not in ids:
            stale.unlink()

    engine = None
    with tempfile.TemporaryDirectory() as tmp:
        for line in voice.lines:
            if only and line.id not in only:
                continue
            out = voice.audio_dir / f"{line.id}.ogg"
            if line.file:
                log(f"{line.id:>4}  [{line.file.relative_to(voice.root)}]")
                to_ogg(line.file, out)
                continue
            log(f"{line.id:>4}  {line.text}")
            engine = engine or get_engine(voice.engine, voice.engine_options, voice.root)
            wav = Path(tmp) / f"{line.id}.wav"
            engine.synthesize(line.text, wav)
            to_ogg(wav, out)

    digest = build_pack(voice.audio_dir, voice.pack_path, voice.md5_path)
    if not only:
        voice.stamp_path.write_text(_source_hash(voice) + "\n")
    return digest


def _source_hash(voice: Voice) -> str:
    return hashlib.sha256(voice.source_path.read_bytes()).hexdigest()


def pack_is_current(voice: Voice) -> bool:
    """True if the pack was fully generated from the voice file as it is now."""
    if not (voice.pack_path.exists() and voice.md5_path.exists() and voice.stamp_path.exists()):
        return False
    return voice.stamp_path.read_text().strip() == _source_hash(voice)
