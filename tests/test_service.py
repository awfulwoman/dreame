import hashlib
import socket
from datetime import date, timedelta
from types import SimpleNamespace
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
                  robot=None, generate_on_start=False, rotate_check_seconds=0)
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
                      "current": False, "md5": None, "url": None,
                      "rotate_days": 3, "lines_with_variants": 0, "next_change": None}

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


def Live(base, valetudo, app, clock):
    return SimpleNamespace(base=base, valetudo=valetudo, app=app, clock=clock)


@pytest.fixture
def live_service(project, fake_engine):
    """The service on a real port, so the fake robot can download from its public URL."""
    valetudo = FakeValetudo()
    port = _free_port()
    clock = {"today": date(2026, 1, 1)}
    app = create_app(settings(project, robot=valetudo.host, public_url=f"http://127.0.0.1:{port}"),
                     today=lambda: clock["today"])
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield Live(f"http://127.0.0.1:{port}", valetudo, app, clock)
    server.should_exit = True
    thread.join(5)
    valetudo.close()


def test_install_has_the_robot_download_from_the_public_url(project, live_service, monkeypatch):
    import httpx2

    from dreame_voice import service

    monkeypatch.setattr(service, "POLL_INTERVAL", 0.05)
    base, valetudo = live_service.base, live_service.valetudo
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


VARIANTS = ("  13: I'm done. Going back home to charge.\n",
            "  13:\n    - Going home.\n    - Back to the dock.\n")


def rotate(live):
    """Run one rotation check; wait for any job it starts."""
    import httpx2

    job = live.app.state.rotate()
    if job:
        with httpx2.Client(base_url=live.base) as c:
            job = wait_for_job(c)
    return job


@pytest.fixture
def rotating(project, live_service, monkeypatch):
    from dreame_voice import service

    monkeypatch.setattr(service, "POLL_INTERVAL", 0.05)
    voice_file = project / "voices" / "beep.yaml"
    voice_file.write_text(voice_file.read_text().replace(*VARIANTS))
    live_service.valetudo.language = "beep"  # the robot is using this voice
    return live_service


def test_rotation_generates_and_installs_the_current_variants(project, rotating, fake_engine):
    job = rotate(rotating)

    assert job["kind"] == "rotate" and job["state"] == "done", job
    voice = load_voice(project, "beep", on=rotating.clock["today"])
    (request,) = rotating.valetudo.requests
    assert request["hash"] == voice.md5_path.read_text().strip()
    assert voice.installed_path.read_text().strip() == request["hash"]
    assert fake_engine.spoken == [voice.lines[1].text]


def test_rotation_does_nothing_when_robot_already_has_todays_pack(rotating):
    rotate(rotating)
    assert rotate(rotating) is None
    assert len(rotating.valetudo.requests) == 1


def test_rotation_moves_to_the_next_variant_when_the_period_changes(project, rotating, fake_engine):
    rotate(rotating)
    first = fake_engine.spoken[-1]
    rotating.clock["today"] = load_voice(project, "beep", on=rotating.clock["today"]).next_change

    job = rotate(rotating)

    assert job["state"] == "done", job
    assert fake_engine.spoken[-1] != first
    assert len(rotating.valetudo.requests) == 2


def test_rotation_waits_for_the_dock_before_installing(project, rotating):
    rotating.valetudo.state = "cleaning"
    job = rotate(rotating)

    assert job["state"] == "done"
    assert any("docked" in line for line in job["log"])
    assert rotating.valetudo.requests == []
    assert (project / "build" / "beep.tar.gz").exists()  # generated ahead of time

    rotating.valetudo.state = "docked"
    assert rotate(rotating)["state"] == "done"
    assert len(rotating.valetudo.requests) == 1


def test_rotation_leaves_a_robot_on_another_voice_alone(rotating):
    rotating.valetudo.language = "en"
    assert rotate(rotating) is None
    assert rotating.valetudo.requests == []


def test_rotation_skips_while_another_job_runs(project, rotating, monkeypatch):
    from dreame_voice import engines

    release = threading.Event()

    class Slow:
        def synthesize(self, text, wav_path):
            release.wait(5)
            from .conftest import make_wav
            make_wav(wav_path)

    monkeypatch.setitem(engines.ENGINES, "fake", lambda options, root: Slow())
    import httpx2
    with httpx2.Client(base_url=rotating.base) as c:
        assert c.post("/voices/beep/generate", headers=AUTH).status_code == 202
        assert rotating.app.state.rotate() is None
        release.set()
        wait_for_job(c)


def test_rotation_without_a_robot_does_nothing(project, fake_engine):
    app = create_app(settings(project))
    assert app.state.rotate() is None


def test_manual_install_records_what_the_robot_has(project, live_service, monkeypatch):
    import httpx2

    from dreame_voice import service

    monkeypatch.setattr(service, "POLL_INTERVAL", 0.05)
    voice = load_voice(project, "beep")
    digest = generate(voice)
    with httpx2.Client(base_url=live_service.base) as c:
        c.post("/voices/beep/install", headers=AUTH)
        assert wait_for_job(c)["state"] == "done"
    assert voice.installed_path.read_text().strip() == digest


def test_voices_show_rotation(project, fake_engine):
    voice_file = project / "voices" / "beep.yaml"
    voice_file.write_text("rotate_days: 3\n" + voice_file.read_text().replace(*VARIANTS))
    today = date(2026, 1, 1)
    with TestClient(create_app(settings(project), today=lambda: today)) as c:
        (v,) = c.get("/voices").json()["voices"]
    assert v["rotate_days"] == 3
    assert v["next_change"] == load_voice(project, "beep", on=today).next_change.isoformat()
    assert v["lines_with_variants"] == 1


def test_settings_read_rotate_check_seconds(project, monkeypatch):
    monkeypatch.setenv("DREAME_API_TOKEN", "t")
    monkeypatch.setenv("DREAME_PUBLIC_URL", "https://x")
    assert Settings.from_env(project).rotate_check_seconds == 3600
    monkeypatch.setenv("DREAME_ROTATE_CHECK_SECONDS", "0")
    assert Settings.from_env(project).rotate_check_seconds == 0
