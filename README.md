# Dreame L10 Pro voicepack generator

I rooted my Dreame L10 Pro vacuum cleaner (model `dreame.vacuum.p2029`) so that I could install Valetudo on it.

While doing this I found the original audio files, which I've saved and documented.

That's when I realised that you can install your own voice packs

I don't own the copyright on the original audio files. They are kept here for academic and research purposes only, blah blah.

## The original sounds

`archive/` holds the manufacturer's audio and my transcription of every prompt, in `archive/sounds.csv`. I spent 20 minutes of my life transcribing these, so be grateful, you little rascals (before we could automate this stuff). `archive/README.md` describes the two sets of audio:

- **Xiaomi's online pack**, listed at https://awsde0.fds.api.xiaomi.com/dreame-product/dreame.vacuum.p2029/voices/soundpackage.json.
- **The firmware's built-in voice**, which uses different recordings and has some extra prompts.

Don't Vacuum Me also has matching sound files at https://builder.dontvacuum.me/pkg/voice/dreame/mc1808/EN.tar.gz. They must be for an older model: a different actress performs them, and the quality is frankly terrible.

## Make your own voice

The Dreame models accept unsigned voice packs (https://robotinfo.dev/detail_dreame.vacuum.p2029_0.html).

`dreame-voice` builds a voice pack from a voice file. There is one voice so far: `glados` (Piper, with a [GLaDOS model](https://github.com/dnhkng/GlaDOS)). Each voice file has its own wording for every prompt, and a text-to-speech engine speaks it. It needs [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra piper           # add --extra xtts for Coqui XTTS (pulls in torch)
uv run dreame-voice new marvin --engine say       # start voices/marvin.yaml
uv run dreame-voice list
uv run dreame-voice generate glados
uv run dreame-voice generate glados --only 13 --only 18   # redo some lines, rebuild the pack
uv run dreame-voice install glados --robot 192.168.1.230  # or set DREAME_ROBOT
uv run pytest
```

### Service

`dreame-voice serve` runs an HTTP service for a reverse proxy, such as `https://voicepacks.example`. It serves every pack all the time. When it starts, it generates each pack that is missing or older than its voice file.

| Endpoint | Auth | |
|---|---|---|
| `GET /health` | | |
| `GET /voices` | | Each voice, whether its pack is current, its MD5 and public URL |
| `GET /packs/<name>.tar.gz` | | The pack. The robot downloads this |
| `POST /voices/<name>/generate` | token | Regenerate in the background |
| `POST /voices/<name>/install` | token | Install on the robot in the background |
| `GET /job` | | The current or last background job, with its log |

One job runs at a time; a second gets `409`. Send the token as `Authorization: Bearer <token>`.

| Variable | |
|---|---|
| `DREAME_API_TOKEN` | Required. Token for the `POST` endpoints |
| `DREAME_PUBLIC_URL` | Required. The URL the robot downloads packs from, for example `https://voicepacks.example` |
| `DREAME_ROBOT` | Valetudo `host[:port]`. Without it, install gives `503` |
| `DREAME_GENERATE_ON_START` | `false` to skip generating at start |
| `PORT` | Default `8000` |

The robot must resolve the public URL's host name through its DNS server, 192.168.1.1. Its `wget` accepts Let's Encrypt certificates.

### Docker

The image `ghcr.io/awfulwoman/dreame` runs the service. It has the `piper` engine, `archive/sounds.csv`, the firmware startup and shutdown sounds, and `voices/`. The `say` engine needs macOS, so voices that use it fail in the image. Build with `--build-arg EXTRAS="piper xtts"` to add XTTS.

```sh
DREAME_API_TOKEN=dev docker compose up --build
curl -X POST -H "Authorization: Bearer dev" localhost:8000/voices/glados/install
```

Keep `/app/models` (downloaded Piper models) and `/app/build` (packs) on volumes. Mount a directory on `/app/voices` to use voice files that are not in the image. The CLI also works in the image, for example `docker run --rm dreame-voice list`.

### Voice files

```yaml
language_id: GLADOS         # optional
engine:
  type: piper               # say | piper | xtts
  model: models/glados.onnx
lines:
  # Robot startup sound.
  0:
    file: archive/audio/firmware/0.ogg     # use this audio as-is
  # Returning to the dock to charge.
  13: I'm done. Going back home to charge.  # speak this
```

The ID decides the file name on the robot (`13` becomes `13.ogg`), so a line can say anything, as long as it has the same purpose as the original. `new` writes every ID with the manufacturer's text, and the original as a comment above it, ready to reword. The startup and shutdown sounds (0 and 200) point at the firmware audio.

A voice must have exactly the IDs in `archive/sounds.csv`. `generate` refuses a voice with a missing or unknown ID. It writes the pack and its MD5 to `build/`.

The robot language ID defaults to the voice name in upper case (`GLADOS`). `EN` and `ZH` are refused, because the robot plays its built-in files for those.

Engine options:

- `say` (macOS): `voice` (required), `rate`
- `piper`: `model` (required), `config`, `model_url`, `config_url`, `speaker_id`, `length_scale`. A missing model or config is downloaded from its URL.
- `xtts`: `speaker_wav` (required; a path or a list of paths to recordings of the voice to clone), `language`, `model`. The XTTS v2 model is under the Coqui Public Model License (non-commercial). Set `COQUI_TOS_AGREED=1` to accept it.

### On the robot

The firmware reads `/data/config/ava/language_in_use`. For `EN` or `ZH` it plays `/audio/<ID>/`. For any other ID it plays `/data/personalized_voice/<ID>/<id>.ogg`.

`dreame-voice install` uses Valetudo's `VoicePackManagementCapability` API. Valetudo has no upload: the robot downloads the pack from a URL and checks its MD5. So the command serves the pack from this machine until the robot has it, then stops.

**Installing a pack deletes every other custom voice on the robot.** The robot empties `/data/personalized_voice/` before it unpacks the new pack, so it holds only one custom voice at a time.


## Other voicepacks

- https://github.com/willemcvu/valetudo-dreame-voicepacks