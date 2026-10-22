"""TTS engines. Each turns text into a WAV file:

    engine = get_engine(type, options, root)
    engine.synthesize(text, wav_path)
"""

from pathlib import Path
from typing import Callable, Protocol


class EngineError(Exception):
    pass


class Engine(Protocol):
    def synthesize(self, text: str, wav_path: Path) -> None: ...


def check_options(engine: str, options: dict, required: set[str], optional: set[str]) -> None:
    missing = required - options.keys()
    if missing:
        raise EngineError(f"{engine}: missing option(s) {', '.join(sorted(missing))}")
    unknown = options.keys() - required - optional
    if unknown:
        raise EngineError(f"{engine}: unknown option(s) {', '.join(sorted(unknown))}")


def resolve(root: Path | None, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() or root is None else root / path


def _say(options, root):
    from .say import SayEngine
    return SayEngine(options)


def _piper(options, root):
    from .piper import PiperEngine
    return PiperEngine(options, root)


def _xtts(options, root):
    from .xtts import XttsEngine
    return XttsEngine(options, root)


ENGINES: dict[str, Callable[[dict, Path | None], Engine]] = {
    "say": _say,
    "piper": _piper,
    "xtts": _xtts,
}


def get_engine(engine_type: str, options: dict, root: Path | None) -> Engine:
    try:
        factory = ENGINES[engine_type]
    except KeyError:
        raise EngineError(f"Unknown engine '{engine_type}'. Known: {', '.join(sorted(ENGINES))}")
    return factory(options, root)
