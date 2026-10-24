"""Voice definitions: voices/<name>.yaml.

    language_id: GLADOS          # optional; defaults to the name in upper case
    rotate_days: 3               # optional; how long each set of variants lasts
    engine:
      type: piper                # plus engine options
      model: models/glados.onnx
    lines:                       # every ID in archive/sounds.csv, no others
      0:
        file: archive/audio/firmware/0.ogg   # use this audio as-is
      13: I'm done. Going back home to charge.   # speak this
      12:                        # variants: one per period, a different one each period
        - Cleaning complete.
        - file: my/recording.ogg

Days are grouped into periods of rotate_days. In each period every line with variants
gets a different variant from the period before.

Everything else derives from the voice name:
  build/<name>/<id>.ogg   generated audio
  build/<name>.tar.gz     pack for the robot
  build/<name>.md5        its MD5, which the robot checks
  build/<name>.source     fingerprint of what the pack was built from
  build/<name>.installed  MD5 of the pack the service last installed on the robot
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from .archive import load_reference

# The firmware plays /audio/<ID>/ for these and ignores /data/personalized_voice
BUILTIN_LANGUAGE_IDS = {"EN", "ZH"}

DEFAULT_ROTATE_DAYS = 3


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
    rotate_days: int = DEFAULT_ROTATE_DAYS
    variant_counts: dict[str, int] = field(default_factory=dict)
    period: int = 0

    @property
    def next_change(self) -> date | None:
        """The first day with different lines, or None if no line has variants."""
        if all(n == 1 for n in self.variant_counts.values()):
            return None
        return date.fromordinal((self.period + 1) * self.rotate_days)

    @property
    def fingerprint(self) -> str:
        """Changes whenever the pack would: engine, options or the lines picked."""
        data = {
            "engine": self.engine,
            "options": self.engine_options,
            "lines": [[line.id, line.text, line.file and str(line.file.relative_to(self.root))]
                      for line in self.lines],
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    @property
    def audio_dir(self) -> Path:
        return self.root / "build" / self.name

    @property
    def pack_path(self) -> Path:
        return self.root / "build" / f"{self.name}.tar.gz"

    @property
    def md5_path(self) -> Path:
        return self.root / "build" / f"{self.name}.md5"

    @property
    def stamp_path(self) -> Path:
        return self.root / "build" / f"{self.name}.source"

    @property
    def installed_path(self) -> Path:
        return self.root / "build" / f"{self.name}.installed"


def voice_names(root: Path) -> list[str]:
    return sorted(p.stem for p in (root / "voices").glob("*.yaml"))


def _parse_variant(root: Path, where: str, line_id: str, value) -> Line:
    if isinstance(value, str) and value.strip():
        return Line(id=line_id, text=value.strip())
    if isinstance(value, dict) and set(value) == {"file"}:
        path = root / value["file"]
        if not path.exists():
            raise ConfigError(f"{where}: line {line_id}: file {value['file']} not found")
        return Line(id=line_id, file=path)
    raise ConfigError(f"{where}: line {line_id} must be text or {{file: <path>}}, not {value!r}")


def _parse_line(root: Path, where: str, line_id: str, value) -> list[Line]:
    if isinstance(value, list):
        if not value:
            raise ConfigError(f"{where}: line {line_id} has an empty list of variants")
        return [_parse_variant(root, where, line_id, v) for v in value]
    return [_parse_variant(root, where, line_id, value)]


def _pick(variants: list[Line], line_id: str, period: int) -> Line:
    # Step one variant per period, so consecutive periods always differ; the offset
    # keeps lines with the same number of variants from moving in lockstep.
    offset = int(hashlib.sha256(line_id.encode()).hexdigest(), 16)
    return variants[(period + offset) % len(variants)]


def load_voice(root: Path, name: str, on: date | None = None) -> Voice:
    """Load voices/<name>.yaml, with the variant of each line for the day `on` (default today)."""
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

    rotate_days = data.get("rotate_days", DEFAULT_ROTATE_DAYS)
    if not isinstance(rotate_days, int) or isinstance(rotate_days, bool) or rotate_days < 1:
        raise ConfigError(f"{where}: rotate_days must be a whole number of days, at least 1")
    period = (on or date.today()).toordinal() // rotate_days

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

    variants = {i: _parse_line(root, where, i, raw_lines[i]) for i in reference}
    return Voice(
        root=root,
        name=name,
        engine=engine_type,
        engine_options=options,
        language_id=language_id,
        lines=[_pick(variants[i], i, period) for i in reference],
        rotate_days=rotate_days,
        variant_counts={i: len(v) for i, v in variants.items()},
        period=period,
    )
