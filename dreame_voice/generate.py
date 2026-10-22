import tempfile
from pathlib import Path

from .audio import wav_to_ogg
from .config import Voice
from .dialog import load_dialog
from .engines import get_engine
from .pack import build_pack


def generate(voice: Voice, only: set[str] | None = None, log=print) -> str:
    """Speak every dialog line into audio/generated/<name>/<id>.ogg, then build the pack.

    With `only`, regenerate just those IDs and keep the rest. Returns the pack's MD5.
    """
    lines = load_dialog(voice.root, voice.dialog)
    engine = get_engine(voice.engine, voice.engine_options, voice.root)
    voice.audio_dir.mkdir(parents=True, exist_ok=True)

    # Drop files for IDs no longer in the dialog, so they don't end up in the pack
    ids = {line.id for line in lines}
    for stale in voice.audio_dir.glob("*.ogg"):
        if stale.stem not in ids:
            stale.unlink()

    with tempfile.TemporaryDirectory() as tmp:
        for line in lines:
            if only and line.id not in only:
                continue
            log(f"{line.id:>4}  {line.text}")
            wav = Path(tmp) / f"{line.id}.wav"
            engine.synthesize(line.text, wav)
            wav_to_ogg(wav, voice.audio_dir / f"{line.id}.ogg")

    return build_pack(voice.audio_dir, voice.pack_path, voice.md5_path)
