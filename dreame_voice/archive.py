"""The manufacturer's prompts: archive/sounds.csv (ID,Filename,Text).

This is the reference for what each ID means, and for which IDs a voice must cover.
"""

import csv
from pathlib import Path

REFERENCE = Path("archive") / "sounds.csv"

# IDs that are sounds, not speech. New voices use the firmware's own audio for these.
SOUND_IDS = {"0", "200"}
FIRMWARE_AUDIO = Path("archive") / "audio" / "firmware"


def load_reference(root: Path) -> dict[str, str]:
    path = root / REFERENCE
    if not path.exists():
        raise FileNotFoundError(f"No reference dialog at {REFERENCE}")
    with path.open(newline="") as f:
        return {row["ID"].strip(): row["Text"].strip() for row in csv.DictReader(f)}
