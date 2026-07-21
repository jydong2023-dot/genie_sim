import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START_GUI = ROOT / "scripts" / "start_gui.sh"


def _fake_command(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def test_run_grants_container_user_access_to_editable_asset_metadata(tmp_path):
    assets = tmp_path / "geniesim_assets"
    egg_info = assets / "geniesim_assets.egg-info"
    egg_info.mkdir(parents=True)
    (assets / "pyproject.toml").write_text("[build-system]\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "sudo-calls"
    docker_calls = tmp_path / "docker-calls"
    _fake_command(bin_dir, "sudo", f'printf "%s\\n" "$*" >> "{calls}"')
    _fake_command(bin_dir, "xhost", "exit 0")
    _fake_command(bin_dir, "docker", f'printf "%s\\n" "$*" >> "{docker_calls}"')

    env = os.environ.copy()
    env.update(
        {
            "GENIESIM_ASSETS_SRC": str(assets),
            "HOME": str(tmp_path / "home"),
            "PATH": f"{bin_dir}:{env['PATH']}",
        }
    )
    result = subprocess.run(
        ["bash", str(START_GUI), "run", "test-container"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    sudo_calls = calls.read_text(encoding="utf-8").splitlines()
    assert f"chmod g+rwx {assets}" in sudo_calls
    assert f"chmod -R g+rwX {egg_info}" in sudo_calls
    docker_run = docker_calls.read_text(encoding="utf-8")
    assert f"--group-add {assets.stat().st_gid}" in docker_run
