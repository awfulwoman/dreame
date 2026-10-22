"""Voice definitions: voices/<name>.yaml.

Everything derives from the voice name:
  voices/<name>.yaml            definition
  audio/generated/<name>/       generated <id>.ogg files
  voicepacks/<name>.tar.gz      pack for the robot
  voicepacks/<name>.md5         its MD5, which the robot checks
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# The firmware plays /audio/<ID>/ for these and ignores /data/personalized_voice
BUILTIN_LANGUAGE_IDS = {"EN", "ZH"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Voice:
    root: Path
    name: str
    dialog: str
    engine: str
    engine_options: dict = field(default_factory=dict)
    language_id: str = ""

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio" / "generated" / self.name

    @property
    def pack_path(self) -> Path:
        return self.root / "voicepacks" / f"{self.name}.tar.gz"

    @property
    def md5_path(self) -> Path:
        return self.root / "voicepacks" / f"{self.name}.md5"


def voice_names(root: Path) -> list[str]:
    return sorted(p.stem for p in (root / "voices").glob("*.yaml"))


def load_voice(root: Path, name: str) -> Voice:
    path = root / "voices" / f"{name}.yaml"
    if not path.exists():
        raise ConfigError(f"No voice definition at voices/{name}.yaml")
    data = yaml.safe_load(path.read_text()) or {}

    if "dialog" not in data:
        raise ConfigError(f"voices/{name}.yaml: missing 'dialog'")
    engine = data.get("engine")
    if not isinstance(engine, dict):
        raise ConfigError(f"voices/{name}.yaml: missing 'engine'")
    options = dict(engine)
    engine_type = options.pop("type", None)
    if not engine_type:
        raise ConfigError(f"voices/{name}.yaml: missing engine 'type'")

    language_id = str(data.get("language_id", name)).upper()
    if language_id in BUILTIN_LANGUAGE_IDS:
        raise ConfigError(
            f"voices/{name}.yaml: language_id {language_id} is a built-in language; "
            "the robot would play its own files instead"
        )

    return Voice(
        root=root,
        name=name,
        dialog=data["dialog"],
        engine=engine_type,
        engine_options=options,
        language_id=language_id,
    )
