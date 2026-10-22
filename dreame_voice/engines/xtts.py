"""Coqui XTTS v2 voice cloning. Needs the `xtts` extra (pulls in torch).

The XTTS v2 model is under the Coqui Public Model License (non-commercial).
Set COQUI_TOS_AGREED=1 to accept it without the interactive prompt.

Options:
  speaker_wav   reference recording(s) of the voice to clone: a path or list of paths (required)
  language      language code (default: en)
  model         Coqui model name (default: XTTS v2)
"""

from pathlib import Path

from . import EngineError, check_options, resolve

DEFAULT_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"


class XttsEngine:
    def __init__(self, options: dict, root: Path | None):
        check_options("xtts", options, required={"speaker_wav"}, optional={"language", "model"})
        wavs = options["speaker_wav"]
        wavs = wavs if isinstance(wavs, list) else [wavs]
        self.speaker_wav = [str(resolve(root, w)) for w in wavs]
        self.language = options.get("language", "en")
        self.model = options.get("model", DEFAULT_MODEL)
        self._tts = None

    def _load(self):
        missing = [w for w in self.speaker_wav if not Path(w).exists()]
        if missing:
            raise EngineError(f"xtts: speaker_wav not found: {', '.join(missing)}")
        try:
            import torch
            from TTS.api import TTS
        except ImportError:
            raise EngineError("xtts: not installed; run `uv sync --extra xtts`")
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self._tts = TTS(self.model).to(device)

    def synthesize(self, text: str, wav_path: Path) -> None:
        if self._tts is None:
            self._load()
        self._tts.tts_to_file(text=text, speaker_wav=self.speaker_wav,
                              language=self.language, file_path=str(wav_path))
