from pathlib import Path

import soundfile as sf
import soxr

# Matches the manufacturer's files: Ogg Vorbis, mono, 16 kHz
SAMPLE_RATE = 16000


def wav_to_ogg(wav: Path, ogg: Path) -> None:
    data, rate = sf.read(wav, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != SAMPLE_RATE:
        mono = soxr.resample(mono, rate, SAMPLE_RATE)
    sf.write(ogg, mono, SAMPLE_RATE, format="OGG", subtype="VORBIS")
