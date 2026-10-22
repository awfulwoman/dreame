# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Archive and documentation of the voice audio from a rooted Dreame L10 Pro (`dreame.vacuum.p2029`), plus scripts that generate replacement voice packs. Not a service; no tests, build, or lint setup. `README.md` holds the filename → spoken-text table (the source of truth for what each numbered file says) and notes on uploading custom packs (`/data/personalized_voice/<lang>/`, Ogg Vorbis).

## Layout

- `audio/manufacturer/xiaomi/` — official English pack from Xiaomi's servers; `audio/manufacturer/firmware/` — built-in English voice copied from the robot's `/audio/EN/` (different recordings, see `audio/README.md`). Both copyrighted; kept for research only. `audio/generated/<voice>/` — script output.
- On the robot, the firmware plays `/audio/{ZH,EN}/` or `/data/personalized_voice/<LANG>/`, chosen by `/data/config/ava/language_in_use` (see `/etc/init.d/play_boot_music.sh`).
- `sounds.csv` — `ID,Filename,Text`; drives generation. `sounds_custom.csv` is a near-copy for edited/custom phrasing (currently not read by any script; scripts hardcode `CSV_SOURCE = "sounds.csv"`).
- `voicepacks/<name>/` — generated `voice_pack.tar.gz` plus an md5 file.

## Generating voice packs

Run from repo root (paths are relative). Deps: `pip install -r requirements.txt` (`requests`, `pydub`; pydub needs `ffmpeg` installed).

- `python glados.py` — fetches TTS per CSV row from `https://glados.c-net.org/generate`, converts wav → ogg, tars. Calls `os.chown(..., 1000, 1000)`, so it fails when not run as root/with permission to chown.
- `python moira.py` — macOS only; uses the `say -v Moira` command, then same wav → ogg → tar flow.

The two scripts are near-duplicates and differ in small ways (tar entry paths: glados uses basenames, moira adds absolute paths via `tar.add(file)`; md5 file named `voice_pack.md5.txt` vs `voicepack.md5.txt`). Packs must contain `<id>.ogg` files at the tar root for the vacuum — check this when touching moira.py. A new voice = copy a script, change `VOICEPACK_NAME` and the TTS step.
