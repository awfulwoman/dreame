"""Install a voice pack through Valetudo's VoicePackManagementCapability.

Valetudo has no upload: it tells the robot a URL, a language and an MD5, and the robot
downloads the pack itself. The CLI serves the pack from this machine for the duration;
the service serves it all the time, at its public URL.

On the Dreame L10 Pro the install empties /data/personalized_voice/ first, so the robot
only ever holds one custom voice.
"""

import json
import socket
import subprocess
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

ENDPOINT = "/api/v2/robot/capabilities/VoicePackManagementCapability"


class InstallError(Exception):
    pass


def local_address_for(robot_host: str) -> str:
    """The address of this machine's interface that routes to the robot."""
    host = robot_host.split(":")[0]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, 80))  # UDP: no packets sent
        return s.getsockname()[0]


class _PackServer:
    """Serves one file, and records when it has been downloaded in full."""

    def __init__(self, pack: Path, host: str):
        self.downloads = 0
        server = self

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path != f"/{pack.name}":
                    self.send_error(404)
                    return
                super().do_GET()
                server.downloads += 1

        self.httpd = ThreadingHTTPServer((host, 0), partial(Handler, directory=str(pack.parent)))
        self.url = f"http://{host}:{self.httpd.server_port}/{pack.name}"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def _request(method: str, url: str, payload: dict | None = None) -> bytes:
    # curl, not urllib: macOS Local Network privacy can block Python from reaching
    # LAN hosts ("No route to host") while curl is allowed.
    cmd = ["curl", "-sS", "--fail-with-body", "--max-time", "10", "-X", method,
           "-H", "Content-Type: application/json"]
    if payload is not None:
        cmd += ["-d", json.dumps(payload)]
    try:
        result = subprocess.run([*cmd, url], capture_output=True)
    except FileNotFoundError:
        raise InstallError("curl is required but was not found")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(errors="replace").strip()
        raise InstallError(f"Could not reach Valetudo at {url}: {detail}")
    return result.stdout


def get_status(robot_host: str) -> dict:
    return json.loads(_request("GET", f"http://{robot_host}{ENDPOINT}"))


def get_state(robot_host: str) -> str:
    """What the robot is doing: docked, cleaning, returning, error, ..."""
    attributes = json.loads(_request("GET", f"http://{robot_host}/api/v2/robot/state/attributes"))
    for attribute in attributes:
        if attribute.get("__class") == "StatusStateAttribute":
            return attribute.get("value", "unknown")
    return "unknown"


def request_install(url: str, md5: str, language_id: str, robot_host: str,
                    downloaded: Callable[[], bool], timeout: float = 120,
                    poll_interval: float = 2, log=print) -> None:
    """Tell the robot to download the pack at `url`, and wait until it uses it.

    `downloaded` says whether the robot has fetched the pack yet: if the robot already
    uses this language, "idle" alone doesn't mean the new pack is installed.
    """
    language = language_id.lower()
    api = f"http://{robot_host}{ENDPOINT}"
    _request("PUT", api, {"action": "download", "url": url,
                          "language": language, "hash": md5})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        status = get_status(robot_host)
        state = status.get("operationStatus", {}).get("type")
        log(f"  {state} {status.get('operationStatus', {}).get('progress', '')}".rstrip())
        if state == "error":
            raise InstallError("Robot reported an error; check the MD5 and that it can reach " + url)
        if (state == "idle" and downloaded()
                and str(status.get("currentLanguage", "")).lower() == language):
            return
    raise InstallError(f"Timed out after {timeout}s waiting for the robot to install the pack")


def install_pack(pack: Path, md5: str, language_id: str, robot_host: str,
                 serve_host: str | None = None, timeout: float = 120,
                 poll_interval: float = 2, log=print) -> None:
    """Serve the pack from this machine while the robot installs it."""
    serve_host = serve_host or local_address_for(robot_host)
    get_status(robot_host)  # fail early if Valetudo isn't there

    with _PackServer(pack, serve_host) as server:
        log(f"Serving {server.url}")
        request_install(server.url, md5, language_id, robot_host,
                        downloaded=lambda: server.downloads > 0,
                        timeout=timeout, poll_interval=poll_interval, log=log)
