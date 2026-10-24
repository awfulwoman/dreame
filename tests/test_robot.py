import hashlib
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dreame_voice.robot import InstallError, _PackServer, install_pack

ENDPOINT = "/api/v2/robot/capabilities/VoicePackManagementCapability"


class FakeValetudo:
    """Behaves like Valetudo on a Dreame: on PUT the 'robot' downloads the URL and checks the MD5."""

    def __init__(self, fail_download=False):
        self.language = "glados"
        self.status = "idle"
        self.requests = []
        self.fail_download = fail_download
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = json.dumps({"currentLanguage": fake.language,
                                   "operationStatus": {"type": fake.status, "metaData": {}}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_PUT(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(payload)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
                threading.Thread(target=fake._download, args=(payload,)).start()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.host = f"127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _download(self, payload):
        self.status = "downloading"
        try:
            data = b"" if self.fail_download else self._fetch(payload["url"])
        except Exception:
            data = b""
        if hashlib.md5(data).hexdigest() == payload["hash"]:
            self.language = payload["language"].lower()
            self.status = "idle"
        else:
            self.status = "error"

    @staticmethod
    def _fetch(url):
        # http.client, so tests can forbid urllib without breaking the fake robot
        import http.client
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
        conn.request("GET", parts.path)
        return conn.getresponse().read()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def valetudo():
    fake = FakeValetudo()
    yield fake
    fake.close()


@pytest.fixture
def pack(tmp_path):
    path = tmp_path / "beep.tar.gz"
    path.write_bytes(b"pretend pack")
    return path, hashlib.md5(b"pretend pack").hexdigest()


def test_install_serves_pack_and_waits_for_robot(valetudo, pack):
    path, digest = pack
    install_pack(path, digest, "BEEP", valetudo.host, serve_host="127.0.0.1", poll_interval=0.05)

    assert valetudo.language == "beep"
    (request,) = valetudo.requests
    assert request["action"] == "download"
    assert request["language"] == "beep"
    assert request["hash"] == digest
    assert request["url"].startswith("http://127.0.0.1:") and request["url"].endswith("/beep.tar.gz")


def test_server_is_stopped_afterwards(valetudo, pack):
    path, digest = pack
    install_pack(path, digest, "BEEP", valetudo.host, serve_host="127.0.0.1", poll_interval=0.05)
    with pytest.raises(OSError):
        urllib.request.urlopen(valetudo.requests[0]["url"], timeout=1)


def test_robot_error_raises(pack):
    fake = FakeValetudo(fail_download=True)
    try:
        path, digest = pack
        with pytest.raises(InstallError, match="error"):
            install_pack(path, digest, "BEEP", fake.host, serve_host="127.0.0.1", poll_interval=0.05)
    finally:
        fake.close()


def test_timeout_raises(valetudo, pack, monkeypatch):
    path, digest = pack
    monkeypatch.setattr(valetudo, "_download", lambda payload: None)
    with pytest.raises(InstallError, match="Timed out"):
        install_pack(path, digest, "BEEP", valetudo.host, serve_host="127.0.0.1",
                     poll_interval=0.05, timeout=0.3)


def test_unreachable_robot_raises(pack):
    path, digest = pack
    with pytest.raises(InstallError, match="Valetudo"):
        install_pack(path, digest, "BEEP", "127.0.0.1:1", serve_host="127.0.0.1", poll_interval=0.05)


def _cli(project, *args, **kwargs):
    from click.testing import CliRunner

    from dreame_voice.cli import main

    return CliRunner().invoke(main, ["--root", str(project), *args], **kwargs)


def test_cli_install_warns_and_asks_first(project, valetudo):
    from dreame_voice.config import load_voice
    from dreame_voice.pack import build_pack

    voice = load_voice(project, "beep")
    voice.audio_dir.mkdir(parents=True)
    (voice.audio_dir / "0.ogg").write_bytes(b"x")
    build_pack(voice.audio_dir, voice.pack_path, voice.md5_path)

    declined = _cli(project, "install", "beep", "--robot", valetudo.host, "--serve-host", "127.0.0.1",
                    input="n\n")
    assert "glados" in declined.output and "replace" in declined.output
    assert valetudo.requests == []

    result = _cli(project, "install", "beep", "--robot", valetudo.host, "--serve-host", "127.0.0.1",
                  "--yes")
    assert result.exit_code == 0, result.output
    assert valetudo.language == "beep"


def test_cli_install_needs_a_generated_pack(project, valetudo):
    result = _cli(project, "install", "beep", "--robot", valetudo.host, "--yes")
    assert result.exit_code != 0
    assert "generate" in result.output


def test_cli_install_reads_robot_from_environment(project, valetudo):
    result = _cli(project, "install", "beep", env={"DREAME_ROBOT": valetudo.host})
    assert "--robot" not in result.output  # host was found; fails later for the missing pack
    assert "generate" in result.output


def test_valetudo_calls_go_through_curl_not_python_sockets(valetudo, pack, monkeypatch):
    # macOS can block Python (but not curl) from the local network
    import urllib.request

    def refuse(*args, **kwargs):
        raise AssertionError("urllib used to reach Valetudo")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    path, digest = pack
    install_pack(path, digest, "BEEP", valetudo.host, serve_host="127.0.0.1", poll_interval=0.05)
    assert valetudo.language == "beep"


def test_request_install_uses_given_url_and_waits_for_download(valetudo, pack):
    from dreame_voice.robot import request_install

    path, digest = pack
    with _PackServer(path, "127.0.0.1") as server:
        request_install(server.url, digest, "BEEP", valetudo.host,
                        downloaded=lambda: server.downloads > 0, poll_interval=0.05)

    assert valetudo.language == "beep"
    assert valetudo.requests[0]["url"] == server.url


def test_request_install_waits_while_robot_still_reports_old_language(valetudo, pack, monkeypatch):
    # Reinstalling the current voice: idle + same language is not success until the pack was fetched
    from dreame_voice.robot import request_install

    path, digest = pack
    valetudo.language = "beep"
    monkeypatch.setattr(valetudo, "_download", lambda payload: None)
    with pytest.raises(InstallError, match="Timed out"):
        request_install("http://127.0.0.1:1/beep.tar.gz", digest, "BEEP", valetudo.host,
                        downloaded=lambda: False, poll_interval=0.05, timeout=0.3)
