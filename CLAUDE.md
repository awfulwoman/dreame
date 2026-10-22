# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Archive and documentation of the voice audio from a rooted Dreame L10 Pro (`dreame.vacuum.p2029`), plus `dreame-voice`, a CLI that generates replacement voice packs. `README.md` holds the filename → spoken-text table and the naming convention.

## Commands

```sh
uv sync --extra piper            # --extra xtts adds Coqui (torch); project pinned to Python 3.13 (coqui needs <3.15)
uv run pytest                    # single test: uv run pytest tests/test_pack.py::test_pack_is_reproducible
uv run dreame-voice list
uv run dreame-voice generate <voice> [--only ID ...]
uv run dreame-voice install <voice> --robot <host>   # or DREAME_ROBOT=<host>
```

## Architecture

`dreame_voice/`: `config.py` (voices/<name>.yaml → `Voice`, which owns all derived paths) → `generate.py` (dialog lines → engine → WAV → `audio.wav_to_ogg` → `pack.build_pack`). Engines in `engines/` share one interface, `synthesize(text, wav_path)`, and are registered in `engines.ENGINES`; heavy deps (piper, torch) are imported lazily so tests run without them. Tests swap in a fake engine via `monkeypatch.setitem(engines.ENGINES, "fake", ...)`.

- Audio conversion uses `soundfile` + `soxr`, not ffmpeg (Homebrew ffmpeg lacks libvorbis). Output matches the manufacturer files: Ogg Vorbis, mono, 16 kHz.
- Packs are reproducible (fixed uid/gid/mtime, gzip mtime 0), so MD5 changes only when audio changes. Entries must be flat `<id>.ogg`.
- Language IDs `EN`/`ZH` are rejected: firmware plays built-in `/audio/<ID>/` for those.

## Data layout

- `audio/manufacturer/xiaomi/` — official English pack from Xiaomi's servers; `audio/manufacturer/firmware/` — built-in English voice copied from the robot's `/audio/EN/` (different recordings, see `audio/README.md`). Both copyrighted; kept for research only. `audio/generated/<voice>/` — tool output.
- `dialog/manufacturer/sounds.csv` — manufacturer phrasing; `dialog/custom/sounds.csv` — custom phrasing (only ID 13 differs so far).
- On the robot (root@192.168.1.102), the firmware plays `/audio/{ZH,EN}/` or `/data/personalized_voice/<LANG>/`, chosen by `/data/config/ava/language_in_use` (see `/etc/init.d/play_boot_music.sh`). Valetudo runs at `/data/valetudo`; its Dreame voice-pack install has the robot download a URL and verify an MD5.
