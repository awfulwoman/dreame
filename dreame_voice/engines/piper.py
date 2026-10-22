"""Piper (offline neural TTS). Needs the `piper` extra.

Options:
  model         path to the .onnx voice model (required)
  config        path to its JSON config (default: <model>.json)
  model_url     download the model from here if it's missing
  config_url    download the config from here if it's missing
  speaker_id    speaker index, for multi-speaker models
  length_scale  < 1 speaks faster, > 1 slower
"""

import urllib.request
import wave
from pathlib import Path

from . import EngineError, check_options, resolve


def _fetch(url: str, dest: Path) -> None:
    print(f"Downloading {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)


class PiperEngine:
    def __init__(self, options: dict, root: Path | None):
        check_options("piper", options, required={"model"},
                      optional={"config", "model_url", "config_url", "speaker_id", "length_scale"})
        self.model = resolve(root, options["model"])
        self.config = resolve(root, options["config"]) if "config" in options else Path(f"{self.model}.json")
        self.model_url = options.get("model_url")
        self.config_url = options.get("config_url")
        self.speaker_id = options.get("speaker_id")
        self.length_scale = options.get("length_scale")
        self._voice = None

    def _load(self):
        for path, url in ((self.model, self.model_url), (self.config, self.config_url)):
            if not path.exists():
                if not url:
                    raise EngineError(f"piper: {path} not found and no download URL given")
                _fetch(url, path)
        try:
            from piper import PiperVoice, SynthesisConfig
        except ImportError:
            raise EngineError("piper: not installed; run `uv sync --extra piper`")
        self._voice = PiperVoice.load(self.model, config_path=self.config)
        self._syn_config = SynthesisConfig(speaker_id=self.speaker_id, length_scale=self.length_scale)

    def synthesize(self, text: str, wav_path: Path) -> None:
        if self._voice is None:
            self._load()
        with wave.open(str(wav_path), "wb") as wav:
            self._voice.synthesize_wav(text, wav, syn_config=self._syn_config)
