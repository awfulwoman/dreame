import hashlib
import socket
import threading
import time

import pytest
import uvicorn
from click.testing import CliRunner
from starlette.testclient import TestClient

from dreame_voice.cli import main
from dreame_voice.config import load_voice
from dreame_voice.generate import generate
from dreame_voice.service import Settings, create_app

from .test_generate import use_fake
from .test_robot import FakeValetudo

TOKEN = "secret-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def settings(project, **overrides):
    values = dict(root=project, api_token=TOKEN, public_url="https://voicepacks.example",
                  robot=None, generate_on_start=False)
    return Settings(**{**values, **overrides})


def wait_for_job(client, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get("/job").json()["job"]
        if job and job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


@pytest.fixture
def fake_engine(monkeypatch):
    return use_fake(monkeypatch)


@pytest.fixture
def client(project, fake_engine):
    with TestClient(create_app(settings(project))) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_voices_lists_pack_state_and_public_url(project, client):
    (before,) = client.get("/voices").json()["voices"]
    assert before == {"name": "beep", "engine": "fake", "language_id": "BEEP",
                      "current": False, "md5": None, "url": None}

    digest = generate(load_voice(project, "beep"))

    (after,) = client.get("/voices").json()["voices"]
    assert after["current"] is True
    assert after["md5"] == digest
    assert after["url"] == "https://voicepacks.example/packs/beep.tar.gz"


def test_invalid_voice_is_listed_with_its_error(project, client):
    (project / "voices" / "broken.yaml").write_text("lines: {}\n")
    voices = {v["name"]: v for v in client.get("/voices").json()["voices"]}
    assert "engine" in voices["broken"]["error"]


def test_pack_is_served_without_auth(project, client):
    voice = load_voice(project, "beep")
    digest = generate(voice)

    response = client.get("/packs/beep.tar.gz")

    assert response.status_code == 200
    assert hashlib.md5(response.content).hexdigest() == digest


def test_missing_pack_is_404(client):
    assert client.get("/packs/beep.tar.gz").status_code == 404
    assert client.get("/packs/nope.tar.gz").status_code == 404
    assert client.get("/packs/..%2Fvoices%2Fbeep.yaml.tar.gz").status_code == 404


@pytest.mark.parametrize("path", ["/voices/beep/generate", "/voices/beep/install"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_actions_need_the_token(client, path, headers):
    assert client.post(path, headers=headers).status_code == 401


def test_generate_runs_in_background_and_reports_the_job(project, client, fake_engine):
    response = client.post("/voices/beep/generate", headers=AUTH)

    assert response.status_code == 202
    assert response.json()["job"]["kind"] == "generate"
    job = wait_for_job(client)
    assert job["state"] == "done", job
    assert fake_engine.spoken == ["I'm done. Going back home to charge."]
    assert client.get("/packs/beep.tar.gz").status_code == 200


def test_generate_unknown_voice_is_404(client):
    assert client.post("/voices/nope/generate", headers=AUTH).status_code == 404


def test_failed_generate_is_reported(project, monkeypatch, client):
    from dreame_voice import engines
    from dreame_voice.engines import EngineError

    class Broken:
        def synthesize(self, text, wav_path):
            raise EngineError("engine on fire")

    monkeypatch.setitem(engines.ENGINES, "fake", lambda options, root: Broken())
    client.post("/voices/beep/generate", headers=AUTH)

    job = wait_for_job(client)
    assert job["state"] == "failed"
    assert "engine on fire" in job["error"]


def test_only_one_job_at_a_time(project, monkeypatch, client):
    from dreame_voice import engines

    release = threading.Event()

    class Slow:
        def synthesize(self, text, wav_path):
            release.wait(5)
            from .conftest import make_wav
            make_wav(wav_path)

    monkeypatch.setitem(engines.ENGINES, "fake", lambda options, root: Slow())
    assert client.post("/voices/beep/generate", headers=AUTH).status_code == 202
    assert client.post("/voices/beep/generate", headers=AUTH).status_code == 409
    release.set()
    assert wait_for_job(client)["state"] == "done"


def test_startup_generates_packs_that_are_not_current(project, fake_engine):
    with TestClient(create_app(settings(project, generate_on_start=True))) as c:
        job = wait_for_job(c)
        assert job["state"] == "done", job
        assert c.get("/voices").json()["voices"][0]["current"] is True
    assert fake_engine.spoken == ["I'm done. Going back home to charge."]

    fake_engine.spoken.clear()
    with TestClient(create_app(settings(project, generate_on_start=True))) as c:
        wait_for_job(c)
    assert fake_engine.spoken == []  # already current


def test_startup_reports_voices_that_failed(project, fake_engine):
    (project / "voices" / "mac.yaml").write_text(
        (project / "voices" / "beep.yaml").read_text().replace("type: fake", "type: nope")
    )
    with TestClient(create_app(settings(project, generate_on_start=True))) as c:
        job = wait_for_job(c)
    assert job["state"] == "failed"
    assert "mac" in job["error"]
    assert (project / "build" / "beep.tar.gz").exists()  # one bad voice doesn't stop the others


def test_install_needs_a_robot(project, client):
    generate(load_voice(project, "beep"))
    response = client.post("/voices/beep/install", headers=AUTH)
    assert response.status_code == 503
    assert "DREAME_ROBOT" in response.json()["error"]


def test_install_needs_a_current_pack(project, fake_engine):
    with TestClient(create_app(settings(project, robot="127.0.0.1:1"))) as c:
        response = c.post("/voices/beep/install", headers=AUTH)
    assert response.status_code == 409
    assert "generate" in response.json()["error"]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_service(project, fake_engine):
    """The service on a real port, so the fake robot can download from its public URL."""
    valetudo = FakeValetudo()
    port = _free_port()
    app = create_app(settings(project, robot=valetudo.host, public_url=f"http://127.0.0.1:{port}"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}", valetudo
    server.should_exit = True
    thread.join(5)
    valetudo.close()


def test_install_has_the_robot_download_from_the_public_url(project, live_service, monkeypatch):
    import httpx2

    from dreame_voice import service

    monkeypatch.setattr(service, "POLL_INTERVAL", 0.05)
    base, valetudo = live_service
    digest = generate(load_voice(project, "beep"))

    with httpx2.Client(base_url=base) as c:
        response = c.post("/voices/beep/install", headers=AUTH)
        assert response.status_code == 202
        job = wait_for_job(c)

    assert job["state"] == "done", job
    assert valetudo.language == "beep"
    (request,) = valetudo.requests
    assert request == {"action": "download", "url": f"{base}/packs/beep.tar.gz",
                       "language": "beep", "hash": digest}


def test_cli_serve_needs_token_and_public_url(project):
    result = CliRunner().invoke(main, ["--root", str(project), "serve"], env={
        "DREAME_API_TOKEN": "", "DREAME_PUBLIC_URL": ""})
    assert result.exit_code != 0
    assert "DREAME_API_TOKEN" in result.output and "DREAME_PUBLIC_URL" in result.output


def test_cli_serve_runs_uvicorn_with_settings_from_environment(project, monkeypatch):
    calls = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(app=app, **kw))
    result = CliRunner().invoke(main, ["--root", str(project), "serve"], env={
        "DREAME_API_TOKEN": TOKEN, "DREAME_PUBLIC_URL": "https://voicepacks.example/",
        "DREAME_ROBOT": "192.168.1.102", "PORT": "9000"})
    assert result.exit_code == 0, result.output
    assert calls["host"] == "0.0.0.0" and calls["port"] == 9000
    s = calls["app"].state.settings
    assert (s.public_url, s.robot, s.root) == ("https://voicepacks.example", "192.168.1.102", project)
