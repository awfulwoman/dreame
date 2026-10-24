# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Archive and documentation of the voice audio from a rooted Dreame L10 Pro (`dreame.vacuum.p2029`), plus `dreame-voice`, a CLI that generates replacement voice packs. `README.md` holds the layout and voice file format; `archive/sounds.csv` holds the prompt transcriptions.

## Commands

```sh
uv sync --extra piper            # --extra xtts adds Coqui (torch); project pinned to Python 3.13 (coqui needs <3.15)
uv run pytest                    # single test: uv run pytest tests/test_pack.py::test_pack_is_reproducible
uv run dreame-voice new <voice> --engine <say|piper|xtts>
uv run dreame-voice list
uv run dreame-voice generate <voice> [--only ID ...]
uv run dreame-voice install <voice> --robot <host>   # or DREAME_ROBOT=<host>
uv run dreame-voice serve        # needs DREAME_API_TOKEN, DREAME_PUBLIC_URL; DREAME_ROBOT for installs
DREAME_API_TOKEN=dev docker compose up --build   # image runs `serve`; volumes /app/build, /app/models
```

`.github/workflows/docker.yml` tests, smoke-tests and pushes `ghcr.io/awfulwoman/dreame` (amd64+arm64). The image is piper-only (`say` is macOS-only; `EXTRAS` build arg adds xtts) and ships only `archive/sounds.csv` + `archive/audio/firmware/` (see `.dockerignore`). The CLI's `install` in a container would need `--network host`; the service instead gives the robot `DREAME_PUBLIC_URL/packs/<name>.tar.gz` (deployed behind the reverse proxy at `https://voicepacks.{{ domainname_infra }}`).

## Architecture

- `archive/` is read-only reference: `archive/sounds.csv` (ID → manufacturer text) defines which IDs exist; `archive/audio/{xiaomi,firmware}/` are copyrighted manufacturer files kept for research. Everything else is generated into `build/` (gitignored).
- `voices/<name>.yaml` holds engine + `lines`, one per ID, each either text (spoken) or `{file: path}` (converted as-is). `config.load_voice` rejects missing/unknown IDs against the archive and returns a `Voice` that owns all derived paths. `new.render_voice` writes a starter file with the original text as comments.
- `generate.py`: lines → engine (`synthesize(text, wav_path)`, created lazily) or file → `audio.to_ogg` → `pack.build_pack`. Engines are registered in `engines.ENGINES`; heavy deps (piper, torch) are imported lazily. Tests swap in a fake engine via `monkeypatch.setitem(engines.ENGINES, "fake", ...)`.
- `robot.py`: `request_install` tells Valetudo's VoicePackManagementCapability to fetch a URL and polls until done; `install_pack` (CLI) wraps it with a temporary HTTP server. Valetudo calls use `curl` because macOS Local Network privacy blocks Python from reaching LAN hosts here.
- `service.py`: Starlette app (`create_app(Settings)`). Serves packs unauthenticated (the robot's wget sends no headers), POST generate/install need the Bearer token and run as one background job at a time (`GET /job`). Startup regenerates packs whose `build/<name>.source` (voice file SHA-256) is stale. Packs are written atomically since they're served while regenerating.

Gotchas:
- Audio conversion uses `soundfile` + `soxr`, not ffmpeg (Homebrew ffmpeg lacks libvorbis). Output matches the manufacturer files: Ogg Vorbis, mono, 16 kHz.
- Packs are reproducible (fixed uid/gid/mtime, gzip mtime 0). Entries must be flat `<id>.ogg`.
- Language IDs `EN`/`ZH` are rejected: firmware plays built-in `/audio/<ID>/` for those.
- Installing a pack wipes all of `/data/personalized_voice/` on the robot; back up first if it holds something not reproducible from this repo.

## Robot

root@192.168.1.102. Firmware plays `/audio/{ZH,EN}/` or `/data/personalized_voice/<LANG>/`, chosen by `/data/config/ava/language_in_use` (see `/etc/init.d/play_boot_music.sh`). Valetudo runs at `/data/valetudo` with Swagger at `/swagger/`.
