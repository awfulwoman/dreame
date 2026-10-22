from pathlib import Path

import click

from .config import ConfigError, load_voice, voice_names
from .engines import EngineError
from .generate import generate as run_generate
from .robot import InstallError, get_status, install_pack


@click.group()
@click.option("--root", type=click.Path(file_okay=False, path_type=Path), default=Path("."),
              show_default=True, help="Repo root holding voices/, dialog/, audio/ and voicepacks/.")
@click.pass_context
def main(ctx, root):
    """Generate Dreame vacuum voice packs."""
    ctx.obj = root.resolve()


@main.command("list")
@click.pass_obj
def list_voices(root):
    """List defined voices."""
    for name in voice_names(root):
        try:
            v = load_voice(root, name)
            click.echo(f"{name:<16} {v.engine:<8} dialog={v.dialog:<14} language_id={v.language_id}")
        except ConfigError as e:
            click.echo(f"{name:<16} INVALID: {e}")


@main.command()
@click.argument("name")
@click.option("--only", multiple=True, metavar="ID", help="Regenerate only these line IDs (repeatable).")
@click.pass_obj
def generate(root, name, only):
    """Generate audio and a voice pack for voice NAME."""
    try:
        voice = load_voice(root, name)
        digest = run_generate(voice, only=set(only) or None, log=click.echo)
    except (ConfigError, EngineError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    click.echo(f"\nPack:        {voice.pack_path.relative_to(root)}")
    click.echo(f"MD5:         {digest}")
    click.echo(f"Language ID: {voice.language_id}")


@main.command()
@click.argument("name")
@click.option("--robot", envvar="DREAME_ROBOT", required=True,
              help="Valetudo host[:port] on the robot. Env: DREAME_ROBOT.")
@click.option("--serve-host", help="Address the robot can reach this machine on. Default: auto-detect.")
@click.option("--yes", is_flag=True, help="Don't ask before replacing the robot's custom voice.")
@click.pass_obj
def install(root, name, robot, serve_host, yes):
    """Install voice NAME's generated pack on the robot through Valetudo."""
    try:
        voice = load_voice(root, name)
    except ConfigError as e:
        raise click.ClickException(str(e))
    if not voice.pack_path.exists() or not voice.md5_path.exists():
        raise click.ClickException(f"No pack for {name}; run `dreame-voice generate {name}` first")
    md5 = voice.md5_path.read_text().strip()

    try:
        current = get_status(robot).get("currentLanguage", "?")
        if not yes:
            click.confirm(
                f"The robot is using '{current}'. Installing will replace ALL custom voices in "
                f"/data/personalized_voice/ with '{voice.language_id.lower()}'. Continue?",
                abort=True,
            )
        install_pack(voice.pack_path, md5, voice.language_id, robot,
                     serve_host=serve_host, log=click.echo)
    except InstallError as e:
        raise click.ClickException(str(e))
    click.echo(f"Installed {name} as language {voice.language_id.lower()}")
