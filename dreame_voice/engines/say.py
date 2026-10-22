"""macOS `say`. Options: voice (required), rate (words per minute)."""

import subprocess
from pathlib import Path

from . import EngineError, check_options


class SayEngine:
    def __init__(self, options: dict):
        check_options("say", options, required={"voice"}, optional={"rate"})
        self.voice = options["voice"]
        self.rate = options.get("rate")

    def synthesize(self, text: str, wav_path: Path) -> None:
        cmd = ["say", "-v", self.voice, "-o", str(wav_path),
               "--file-format=WAVE", "--data-format=LEI16@22050"]
        if self.rate:
            cmd += ["-r", str(self.rate)]
        # "--" so text starting with "-" isn't read as a flag
        result = subprocess.run([*cmd, "--", text], capture_output=True, text=True)
        if result.returncode != 0:
            raise EngineError(f"say failed: {result.stderr.strip()}")
