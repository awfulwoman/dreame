"""Voice definitions: voices/<name>.yaml.

    language_id: GLADOS          # optional; defaults to the name in upper case
    engine:
      type: piper                # plus engine options
      model: models/glados.onnx
    lines:                       # every ID in archive/sounds.csv, no others
      0:
        file: archive/audio/firmware/0.ogg   # use this audio as-is
      13: I'm done. Going back home to charge.   # speak this

Everything else derives from the voice name:
  build/<name>/<id>.ogg   generated audio
  build/<name>.tar.gz     pack for the robot
  build/<name>.md5        its MD5, which the robot checks
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .archive import load_reference

# The firmware plays /audio/<ID>/ for these and ignores /data/personalized_voice
BUILTIN_LANGUAGE_IDS = {"EN", "ZH"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Line:
    id: str
    text: str | None = None
    file: Path | None = None


@dataclass(frozen=True)
class Voice:
    root: Path
    name: str
    engine: str
    engine_options: dict = field(default_factory=dict)
    language_id: str = ""
    lines: list[Line] = field(default_factory=list)

    @property
    def audio_dir(self) -> Path:
        return self.root / "build" / self.name

    @property
    def pack_path(self) -> Path:
        return self.root / "build" / f"{self.name}.tar.gz"

    @property
    def md5_path(self) -> Path:
        return self.root / "build" / f"{self.name}.md5"


def voice_names(root: Path) -> list[str]:
    return sorted(p.stem for p in (root / "voices").glob("*.yaml"))


def _parse_line(root: Path, where: str, line_id: str, value) -> Line:
    if isinstance(value, str) and value.strip():
        return Line(id=line_id, text=value.strip())
    if isinstance(value, dict) and set(value) == {"file"}:
        path = root / value["file"]
        if not path.exists():
            raise ConfigError(f"{where}: line {line_id}: file {value['file']} not found")
        return Line(id=line_id, file=path)
    raise ConfigError(f"{where}: line {line_id} must be text or {{file: <path>}}, not {value!r}")


def load_voice(root: Path, name: str) -> Voice:
    where = f"voices/{name}.yaml"
    path = root / where
    if not path.exists():
        raise ConfigError(f"No voice definition at {where}")
    data = yaml.safe_load(path.read_text()) or {}

    engine = data.get("engine")
    if not isinstance(engine, dict):
        raise ConfigError(f"{where}: missing 'engine'")
    options = dict(engine)
    engine_type = options.pop("type", None)
    if not engine_type:
        raise ConfigError(f"{where}: missing engine 'type'")

    language_id = str(data.get("language_id", name)).upper()
    if language_id in BUILTIN_LANGUAGE_IDS:
        raise ConfigError(
            f"{where}: language_id {language_id} is a built-in language; "
            "the robot would play its own files instead"
        )

    raw_lines = data.get("lines")
    if not isinstance(raw_lines, dict):
        raise ConfigError(f"{where}: missing 'lines'")
    raw_lines = {str(k): v for k, v in raw_lines.items()}
    reference = load_reference(root)
    missing = [i for i in reference if i not in raw_lines]
    if missing:
        raise ConfigError(f"{where}: missing lines for ID(s) {', '.join(missing)}")
    unknown = [i for i in raw_lines if i not in reference]
    if unknown:
        raise ConfigError(f"{where}: unknown ID(s) {', '.join(unknown)}; not in archive/sounds.csv")

    return Voice(
        root=root,
        name=name,
        engine=engine_type,
        engine_options=options,
        language_id=language_id,
        lines=[_parse_line(root, where, i, raw_lines[i]) for i in reference],
    )
