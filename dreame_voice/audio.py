from pathlib import Path

import soundfile as sf
import soxr

# Matches the manufacturer's files: Ogg Vorbis, mono, 16 kHz
SAMPLE_RATE = 16000


def to_ogg(src: Path, ogg: Path) -> None:
    """Convert any audio libsndfile reads (WAV, Ogg, FLAC, ...) to the robot's format."""
    data, rate = sf.read(src, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != SAMPLE_RATE:
        mono = soxr.resample(mono, rate, SAMPLE_RATE)
    sf.write(ogg, mono, SAMPLE_RATE, format="OGG", subtype="VORBIS")
