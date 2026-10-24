"""HTTP service: serves voice packs all the time, and generates and installs them on request.

    GET  /health
    GET  /voices                  every voice, its pack state and public pack URL
    GET  /packs/<name>.tar.gz     the pack; the robot downloads this, so no auth
    POST /voices/<name>/generate  Bearer token; runs in the background
    POST /voices/<name>/install   Bearer token; runs in the background
    GET  /job                     the current or last background job

It runs behind a reverse proxy: the robot is given DREAME_PUBLIC_URL/packs/<name>.tar.gz.
One job runs at a time. On start it generates every pack that isn't current.
"""

import hmac
import os
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from .config import ConfigError, Voice, load_voice, voice_names
from .generate import generate, pack_is_current
from .robot import get_status, request_install

POLL_INTERVAL = 2


@dataclass(frozen=True)
class Settings:
    root: Path
    api_token: str
    public_url: str
    robot: str | None = None
    generate_on_start: bool = True

    @classmethod
    def from_env(cls, root: Path) -> "Settings":
        env = {k: os.environ.get(k, "").strip() for k in
               ("DREAME_API_TOKEN", "DREAME_PUBLIC_URL", "DREAME_ROBOT", "DREAME_GENERATE_ON_START")}
        missing = [k for k in ("DREAME_API_TOKEN", "DREAME_PUBLIC_URL") if not env[k]]
        if missing:
            raise ConfigError(f"Set {' and '.join(missing)}")
        return cls(
            root=root,
            api_token=env["DREAME_API_TOKEN"],
            public_url=env["DREAME_PUBLIC_URL"].rstrip("/"),
            robot=env["DREAME_ROBOT"] or None,
            generate_on_start=env["DREAME_GENERATE_ON_START"].lower() not in ("0", "false", "no"),
        )


class Busy(Exception):
    pass


class Jobs:
    """Runs one background job at a time and keeps the latest one for GET /job."""

    def __init__(self):
        self._lock = threading.Lock()
        self.current: dict | None = None

    def start(self, kind: str, voice: str, work: Callable[[Callable[[str], None]], None]) -> dict:
        with self._lock:
            if self.current and self.current["state"] == "running":
                raise Busy(f"{self.current['kind']} {self.current['voice']} is running")
            job = {"kind": kind, "voice": voice, "state": "running", "log": [], "error": None,
                   "started": time.time(), "finished": None}
            self.current = job
        threading.Thread(target=self._run, args=(job, work), daemon=True).start()
        return job

    @staticmethod
    def _run(job: dict, work) -> None:
        try:
            work(job["log"].append)
            job["state"] = "done"
        except Exception as e:
            job["error"] = str(e)
            job["state"] = "failed"
        job["finished"] = time.time()


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def create_app(settings: Settings) -> Starlette:
    root = settings.root
    jobs = Jobs()
    downloads: Counter[str] = Counter()

    def pack_url(voice: Voice) -> str:
        return f"{settings.public_url}/packs/{voice.pack_path.name}"

    def authorised(request: Request) -> bool:
        given = request.headers.get("authorization", "")
        return hmac.compare_digest(given.encode(), f"Bearer {settings.api_token}".encode())

    def find_voice(name: str) -> Voice | None:
        return load_voice(root, name) if name in voice_names(root) else None

    def generate_stale(log) -> None:
        failed = []
        for name in voice_names(root):
            try:
                voice = load_voice(root, name)
                if pack_is_current(voice):
                    continue
                log(f"Generating {name}")
                generate(voice, log=log)
            except Exception as e:
                log(f"{name}: {e}")
                failed.append(f"{name}: {e}")
        if failed:
            raise RuntimeError("; ".join(failed))

    @asynccontextmanager
    async def lifespan(app):
        if settings.generate_on_start:
            jobs.start("generate", "*", generate_stale)
        yield

    async def health(request):
        return JSONResponse({"status": "ok"})

    async def voices(request):
        result = []
        for name in voice_names(root):
            try:
                voice = load_voice(root, name)
            except ConfigError as e:
                result.append({"name": name, "error": str(e)})
                continue
            has_pack = voice.pack_path.exists() and voice.md5_path.exists()
            result.append({
                "name": name,
                "engine": voice.engine,
                "language_id": voice.language_id,
                "current": pack_is_current(voice),
                "md5": voice.md5_path.read_text().strip() if has_pack else None,
                "url": pack_url(voice) if has_pack else None,
            })
        return JSONResponse({"voices": result})

    async def pack(request):
        name = request.path_params["name"]
        if name not in voice_names(root):
            return _error(404, "No such voice")
        path = root / "build" / f"{name}.tar.gz"
        if not path.exists():
            return _error(404, f"No pack for {name} yet")
        if request.method == "GET":
            downloads[name] += 1
        return FileResponse(path, media_type="application/gzip")

    def action(handler):
        async def endpoint(request):
            if not authorised(request):
                return _error(401, "Missing or wrong Bearer token")
            try:
                voice = find_voice(request.path_params["name"])
            except ConfigError as e:
                return _error(409, str(e))
            if voice is None:
                return _error(404, "No such voice")
            try:
                return handler(voice)
            except Busy as e:
                return _error(409, str(e))
        return endpoint

    def start_generate(voice: Voice):
        job = jobs.start("generate", voice.name, lambda log: generate(voice, log=log))
        return JSONResponse({"job": job}, status_code=202)

    def start_install(voice: Voice):
        if not settings.robot:
            return _error(503, "No robot configured; set DREAME_ROBOT")
        if not pack_is_current(voice):
            return _error(409, f"Pack for {voice.name} is missing or out of date; generate it first")
        md5 = voice.md5_path.read_text().strip()

        def work(log):
            get_status(settings.robot)  # fail early if Valetudo isn't there
            before = downloads[voice.name]
            url = pack_url(voice)
            log(f"Robot will download {url}")
            request_install(url, md5, voice.language_id, settings.robot,
                            downloaded=lambda: downloads[voice.name] > before,
                            poll_interval=POLL_INTERVAL, log=log)
            log(f"Installed {voice.name} as language {voice.language_id.lower()}")

        job = jobs.start("install", voice.name, work)
        return JSONResponse({"job": job}, status_code=202)

    async def job(request):
        return JSONResponse({"job": jobs.current})

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/voices", voices),
            Route("/packs/{name}.tar.gz", pack),
            Route("/voices/{name}/generate", action(start_generate), methods=["POST"]),
            Route("/voices/{name}/install", action(start_install), methods=["POST"]),
            Route("/job", job),
        ],
        lifespan=lifespan,
    )
    app.state.settings = settings
    return app
