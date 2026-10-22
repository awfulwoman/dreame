"""Install a voice pack through Valetudo's VoicePackManagementCapability.

Valetudo has no upload: it tells the robot a URL, a language and an MD5, and the robot
downloads the pack itself. So we serve the pack from this machine for the duration.

On the Dreame L10 Pro the install empties /data/personalized_voice/ first, so the robot
only ever holds one custom voice.
"""

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError) as e:
        raise InstallError(f"Could not reach Valetudo at {url}: {e}")


def get_status(robot_host: str) -> dict:
    return json.loads(_request("GET", f"http://{robot_host}{ENDPOINT}"))


def install_pack(pack: Path, md5: str, language_id: str, robot_host: str,
                 serve_host: str | None = None, timeout: float = 120,
                 poll_interval: float = 2, log=print) -> None:
    language = language_id.lower()
    serve_host = serve_host or local_address_for(robot_host)
    api = f"http://{robot_host}{ENDPOINT}"

    get_status(robot_host)  # fail early if Valetudo isn't there

    with _PackServer(pack, serve_host) as server:
        log(f"Serving {server.url}")
        _request("PUT", api, {"action": "download", "url": server.url,
                              "language": language, "hash": md5})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(poll_interval)
            status = get_status(robot_host)
            state = status.get("operationStatus", {}).get("type")
            log(f"  {state} {status.get('operationStatus', {}).get('progress', '')}".rstrip())
            if state == "error":
                raise InstallError("Robot reported an error; check the MD5 and that it can reach " + server.url)
            if (state == "idle" and server.downloads
                    and str(status.get("currentLanguage", "")).lower() == language):
                return
        raise InstallError(f"Timed out after {timeout}s waiting for the robot to install the pack")
