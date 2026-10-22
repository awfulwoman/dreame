"""Start a voice file: every ID with the manufacturer's text, the original as a comment above."""

from pathlib import Path

import yaml

from .archive import FIRMWARE_AUDIO, SOUND_IDS, load_reference


def _scalar(text: str) -> str:
    # Let PyYAML pick safe quoting, then strip the document end marker it adds
    return yaml.safe_dump(text, allow_unicode=True, width=1000).removesuffix("\n...\n").strip()


def render_voice(root: Path, engine_type: str) -> str:
    out = [
        "# language_id: NAME           # optional; defaults to the file name in upper case",
        "engine:",
        f"  type: {engine_type}",
        "  # engine options; see README",
        "lines:",
    ]
    for line_id, original in load_reference(root).items():
        out.append(f"  # {original}")
        if line_id in SOUND_IDS:
            out.append(f"  {line_id}:")
            out.append(f"    file: {(FIRMWARE_AUDIO / f'{line_id}.ogg').as_posix()}")
        else:
            out.append(f"  {line_id}: {_scalar(original)}")
    return "\n".join(out) + "\n"
