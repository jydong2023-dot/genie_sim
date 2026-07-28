#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Open one geniesim_benchmark scene in Isaac Sim without an inference server."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
PACKAGE_SRC = PACKAGE_ROOT / "src"
if PACKAGE_SRC.is_dir() and str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

DEFAULT_CONFIG = "g2op_if_pick_block_color"
SKIP_CONFIG_NAMES = frozenset({"config.yaml", "template.yaml", "teleop.yaml"})
CONTAINER_ASSET_PREFIX = "@/geniesim_assets/"
DEFAULT_ISAAC_SIM_ROOT = Path("/isaac-sim")


def isaacsim_numpy_library_paths(isaac_root: Path = DEFAULT_ISAAC_SIM_ROOT) -> list[Path]:
    """Find Isaac Sim NumPy native-library directories needed by Kit extensions."""
    isaac_root = isaac_root.expanduser()
    candidates = [
        *sorted(isaac_root.glob("extscache/omni.kit.pip_archive-*/pip_prebundle/numpy.libs")),
        *sorted(isaac_root.glob("kit/python/lib/python*/site-packages/numpy.libs")),
    ]
    return [path for path in candidates if path.is_dir()]


def prepend_library_paths(env: dict[str, str], paths: Iterable[Path]) -> dict[str, str]:
    updated = dict(env)
    existing = [item for item in updated.get("LD_LIBRARY_PATH", "").split(":") if item]
    existing_set = set(existing)
    prepend: list[str] = []
    for path in paths:
        value = str(path)
        if value in existing_set or value in prepend:
            continue
        prepend.append(value)

    merged = [*prepend, *existing]
    if merged:
        updated["LD_LIBRARY_PATH"] = ":".join(merged)
    return updated


def prepare_isaacsim_numpy_runtime_env(
    env: dict[str, str],
    *,
    isaac_root: Path = DEFAULT_ISAAC_SIM_ROOT,
) -> dict[str, str]:
    if env.get("GENIESIM_NUMPY_LIBS_READY") == "1":
        return dict(env)

    paths = isaacsim_numpy_library_paths(isaac_root)
    if not paths:
        return dict(env)

    updated = prepend_library_paths(env, paths)
    if updated.get("LD_LIBRARY_PATH") != env.get("LD_LIBRARY_PATH"):
        updated["GENIESIM_NUMPY_LIBS_READY"] = "1"
    return updated


def reexec_with_isaacsim_numpy_libs(isaac_root: Path = DEFAULT_ISAAC_SIM_ROOT) -> None:
    """Restart under an LD_LIBRARY_PATH that can import Kit's bundled NumPy."""
    if not isaac_root.is_dir():
        return

    current_env = dict(os.environ)
    updated_env = prepare_isaacsim_numpy_runtime_env(current_env, isaac_root=isaac_root)
    if updated_env.get("LD_LIBRARY_PATH") == current_env.get("LD_LIBRARY_PATH"):
        return

    os.execvpe(sys.executable, [sys.executable, *sys.argv], updated_env)


@dataclass(frozen=True)
class SceneSelection:
    config_name: str
    config_path: Path
    task_name: str
    sub_task_name: str
    instance_id: int
    robot_cfg: str
    robot_name: str
    robot_prim_path: str
    robot_usd_path: Path
    scene_usd_path: Path
    workspace_usd_path: Path | None
    robot_position: list[float]
    robot_quaternion: list[float]
    camera_target: list[float]

    def to_jsonable(self) -> dict:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        return data


def package_root() -> Path:
    return PACKAGE_ROOT


def default_config_dir() -> Path:
    return package_root() / "src" / "geniesim_benchmark" / "config"


def discover_repo_root(start: Path | None = None) -> Path:
    env_root = os.environ.get("GENIESIM_REPO_ROOT") or os.environ.get("SIM_REPO_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "source" / "geniesim_benchmark").is_dir() and (candidate / "VERSION").is_file():
            return candidate
    return package_root().parent.parent.resolve()


def default_assets_root(repo_root: Path | None = None) -> Path:
    for key in ("GENIESIM_ASSETS_PATH", "GENIESIM_ASSETS_DIR", "SIM_ASSETS"):
        value = os.environ.get(key)
        if value:
            return Path(value).expanduser().resolve()

    try:
        from geniesim_assets import ASSETS_PATH

        if ASSETS_PATH:
            return Path(ASSETS_PATH).expanduser().resolve()
    except ModuleNotFoundError:
        pass

    if repo_root is not None:
        sibling = repo_root.parent / "geniesim_assets"
        if sibling.exists():
            return sibling.resolve()

    return Path("/geniesim_assets")


def iter_task_configs(config_dir: Path) -> list[Path]:
    return [
        path.resolve()
        for path in sorted(config_dir.glob("*.yaml"))
        if path.name not in SKIP_CONFIG_NAMES and not path.name.startswith("_")
    ]


def resolve_config_path(config: str | Path, config_dir: Path) -> Path:
    value = str(config)
    raw = Path(value).expanduser()
    exact_candidates = []
    if raw.suffix:
        exact_candidates.append(raw)
        if not raw.is_absolute():
            exact_candidates.append(config_dir / raw)
    else:
        exact_candidates.append(raw.with_suffix(".yaml"))
        if not raw.is_absolute():
            exact_candidates.append(config_dir / f"{value}.yaml")

    for candidate in exact_candidates:
        if candidate.is_file():
            return candidate.resolve()

    needle = value.lower()
    matches = [path for path in iter_task_configs(config_dir) if needle in path.stem.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"No benchmark config matches {value!r} under {config_dir}")
    names = ", ".join(path.stem for path in matches[:10])
    if len(matches) > 10:
        names += ", ..."
    raise ValueError(f"Config selector {value!r} is ambiguous: {names}")


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _asset_path(value: str, assets_root: Path) -> Path:
    if not value:
        raise ValueError("asset path cannot be empty")
    raw = Path(value)
    if raw.is_absolute() and str(raw).startswith(str(assets_root)):
        return raw
    return assets_root / value.lstrip("/")


def _select_robot_pose(robot_pose: dict, scene_cfg: dict) -> tuple[list[float], list[float]]:
    if "position" in robot_pose and "quaternion" in robot_pose:
        return list(robot_pose["position"]), list(robot_pose["quaternion"])

    workspace_name = str(scene_cfg.get("scene_id", "")).rstrip("/").split("/")[-1]
    if workspace_name and workspace_name in robot_pose:
        pose = robot_pose[workspace_name]
        return list(pose["position"]), list(pose["quaternion"])

    for pose in robot_pose.values():
        if isinstance(pose, dict) and "position" in pose and "quaternion" in pose:
            return list(pose["position"]), list(pose["quaternion"])

    return [0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]


def _camera_target(scene_cfg: dict, robot_position: list[float]) -> list[float]:
    function_spaces = scene_cfg.get("function_space_objects", {}) or {}
    workspace_name = str(scene_cfg.get("scene_id", "")).rstrip("/").split("/")[-1]
    candidates = []
    if workspace_name:
        candidates.append(function_spaces.get(workspace_name))
    candidates.extend(function_spaces.values())
    for item in candidates:
        if isinstance(item, dict) and isinstance(item.get("position"), list):
            return [float(v) for v in item["position"][:3]]
    return [float(robot_position[0] - 2.5), float(robot_position[1]), 0.8]


def _resolve_workspace_usd(
    scene_cfg: dict,
    benchmark_conf_dir: Path,
    sub_task_name: str,
    instance_id: int,
) -> Path | None:
    if not sub_task_name:
        return None
    override_root = scene_cfg.get("sub_usd_override_root", "")
    if override_root:
        root = Path(str(override_root)).expanduser()
        if not root.is_absolute():
            root = benchmark_conf_dir / root
        return root / str(instance_id) / "scene.usda"
    return benchmark_conf_dir / "llm_task" / sub_task_name / str(instance_id) / "scene.usda"


def load_scene_selection(
    config: str | Path = DEFAULT_CONFIG,
    *,
    config_dir: Path | None = None,
    assets_root: Path | None = None,
    instance_id: int = 0,
) -> SceneSelection:
    config_dir = (config_dir or default_config_dir()).expanduser().resolve()
    config_path = resolve_config_path(config, config_dir)
    package_dir = config_dir.parent
    assets_root = (assets_root or default_assets_root(discover_repo_root(config_dir))).expanduser().resolve()

    benchmark_cfg = (_read_yaml(config_path).get("benchmark", {}) or {})
    task_name = benchmark_cfg.get("task_name", "")
    sub_task_name = benchmark_cfg.get("sub_task_name", "")
    if not task_name:
        raise ValueError(f"{config_path} does not define benchmark.task_name")

    eval_task_path = package_dir / "benchmark" / "config" / "eval_tasks" / f"{task_name}.json"
    eval_task = _read_json(eval_task_path)
    robot_cfg = (eval_task.get("robot", {}) or {}).get("robot_cfg", "G1_120s.json")
    robot_cfg_path = package_dir / "app" / "robot_cfg" / robot_cfg
    robot_json = _read_json(robot_cfg_path).get("robot", {}) or {}
    scene_cfg = eval_task.get("scene", {}) or {}

    robot_position, robot_quaternion = _select_robot_pose(
        (eval_task.get("robot", {}) or {}).get("robot_init_pose", {}) or {},
        scene_cfg,
    )
    benchmark_conf_dir = package_dir / "benchmark" / "config"
    workspace_usd = _resolve_workspace_usd(scene_cfg, benchmark_conf_dir, sub_task_name, instance_id)

    return SceneSelection(
        config_name=config_path.stem,
        config_path=config_path,
        task_name=task_name,
        sub_task_name=sub_task_name,
        instance_id=instance_id,
        robot_cfg=robot_cfg,
        robot_name=str(robot_json.get("robot_name", robot_cfg.removesuffix(".json"))),
        robot_prim_path=str(robot_json.get("base_prim_path", "/genie")),
        robot_usd_path=_asset_path(str(robot_json.get("robot_usd", "")), assets_root),
        scene_usd_path=_asset_path(str(scene_cfg.get("scene_usd", "")), assets_root),
        workspace_usd_path=workspace_usd,
        robot_position=robot_position,
        robot_quaternion=robot_quaternion,
        camera_target=_camera_target(scene_cfg, robot_position),
    )


def prepare_workspace_usd(source: Path, *, assets_root: Path, output_dir: Path) -> Path:
    """Rewrite container-only /geniesim_assets references for host viewing."""
    source = source.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / source.name
    text = source.read_text(encoding="utf-8")
    replacement = f"@{assets_root.expanduser().resolve().as_posix().rstrip('/')}/"
    target.write_text(text.replace(CONTAINER_ASSET_PREFIX, replacement), encoding="utf-8")
    return target


def build_docker_exec_command(
    script: Path,
    *,
    container: str = "geniesim3",
    uid: int = 1000,
    gid: int = 1000,
    args: Iterable[str] = (),
) -> list[str]:
    return [
        "docker",
        "exec",
        "-it",
        "-u",
        f"{uid}:{gid}",
        "-e",
        "HOME=/home/isaac-sim",
        "-e",
        "SIM_REPO_ROOT=/workspace",
        "-e",
        "GENIESIM_REPO_ROOT=/workspace",
        "-e",
        "GENIESIM_ASSETS_PATH=/geniesim_assets",
        "-w",
        "/workspace",
        container,
        str(script),
        *list(args),
    ]


def _check_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def _camera_eye(target: list[float]) -> list[float]:
    return [target[0] + 2.8, target[1] - 3.0, target[2] + 1.8]


def ensure_simulation_app_available() -> None:
    try:
        from isaacsim import SimulationApp
    except ModuleNotFoundError as exc:
        raise RuntimeError("isaacsim is not importable in this Python environment") from exc
    if not callable(SimulationApp):
        raise RuntimeError(
            "isaacsim.SimulationApp is not available in this Python environment. "
            "Run this viewer inside the GenieSim container via "
            "`geniesim docker into` and `/workspace/source/geniesim_benchmark/scripts/open_benchmark_scene.bash`, "
            "or run the Bash wrapper on the host while the geniesim3 container is running."
        )


def enable_isaac_extension(extension_name: str, *, enable_extension=None) -> None:
    if enable_extension is None:
        from isaacsim.core.utils.extensions import enable_extension

    enable_extension(extension_name)


def launch_viewer(
    selection: SceneSelection,
    *,
    repo_root: Path,
    assets_root: Path,
    headless: bool = False,
    render_mode: str = "RaytracedLighting",
    camera_eye: list[float] | None = None,
    camera_target: list[float] | None = None,
    prepared_dir: Path | None = None,
    max_frames: int | None = None,
    enable_physics_inspector_ui: bool = True,
) -> int:
    os.environ.setdefault("GENIESIM_REPO_ROOT", str(repo_root))
    os.environ.setdefault("SIM_REPO_ROOT", str(repo_root))
    os.environ.setdefault("GENIESIM_ASSETS_PATH", str(assets_root))
    os.environ.setdefault("GENIESIM_KIT_RUNTIME_DIR", str(repo_root / ".kit"))
    os.environ.setdefault("GENIESIM_OMNI_DOCUMENTS_DIR", str(repo_root / "Documents"))

    _check_file(selection.robot_usd_path, "robot USD")
    _check_file(selection.scene_usd_path, "background USD")
    if selection.workspace_usd_path is not None:
        _check_file(selection.workspace_usd_path, "workspace USD")

    ensure_simulation_app_available()
    from geniesim_benchmark.app.workflow import AppLauncher

    app_launcher = AppLauncher(SimpleNamespace(headless=headless, render_mode=render_mode))
    simulation_app = app_launcher.app
    if enable_physics_inspector_ui and not headless:
        try:
            enable_isaac_extension("omni.physx.supportui")
            simulation_app.update()
        except Exception as exc:
            print(f"Warning: could not enable omni.physx.supportui: {exc}", file=sys.stderr)

    try:
        from isaacsim.core.api import World
        from isaacsim.core.prims import SingleXFormPrim
        from isaacsim.core.utils.stage import add_reference_to_stage, update_stage
        from isaacsim.core.utils.viewports import set_camera_view

        world = World(stage_units_in_meters=1, physics_dt=1.0 / 120.0, rendering_dt=1.0 / 60.0)
        add_reference_to_stage(str(selection.robot_usd_path), selection.robot_prim_path)
        add_reference_to_stage(str(selection.scene_usd_path), "/World")

        workspace_path = selection.workspace_usd_path
        if workspace_path is not None:
            if assets_root.resolve() != Path("/geniesim_assets"):
                prepared_dir = prepared_dir or Path(tempfile.gettempdir()) / "geniesim_benchmark_scene_viewer"
                workspace_path = prepare_workspace_usd(
                    workspace_path,
                    assets_root=assets_root,
                    output_dir=prepared_dir / selection.sub_task_name / str(selection.instance_id),
                )
            add_reference_to_stage(str(workspace_path), "/Workspace")

        SingleXFormPrim(
            prim_path=selection.robot_prim_path,
            position=selection.robot_position,
            orientation=selection.robot_quaternion,
        )
        update_stage()
        target = camera_target or selection.camera_target
        eye = camera_eye or _camera_eye(target)
        set_camera_view(eye=eye, target=target, camera_prim_path="/OmniverseKit_Persp")

        print(f"Opened config: {selection.config_name}")
        print(f"Task: {selection.task_name} / {selection.sub_task_name or '<base>'} / instance {selection.instance_id}")
        print(f"Robot: {selection.robot_name} ({selection.robot_cfg})")
        print(f"Background: {selection.scene_usd_path}")
        if workspace_path is not None:
            print(f"Workspace: {workspace_path}")
        print("Close the Isaac Sim window or press Ctrl-C to exit.")

        world.reset()
        world.play()
        frame = 0
        while simulation_app.is_running():
            world.step(render=not headless)
            frame += 1
            if max_frames is not None and frame >= max_frames:
                break
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        simulation_app.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Benchmark config basename, path, or unique substring")
    parser.add_argument("--config-dir", type=Path, default=None, help="Directory containing benchmark YAML configs")
    parser.add_argument("--repo-root", type=Path, default=None, help="Genie Sim repo root used for runtime tokens")
    parser.add_argument("--assets-root", type=Path, default=None, help="Actual geniesim_assets directory on this host")
    parser.add_argument("--instance-id", type=int, default=0, help="Numeric llm_task scene instance to load")
    parser.add_argument("--headless", action="store_true", help="Launch without GUI, useful for smoke tests")
    parser.add_argument("--render-mode", default="RaytracedLighting", help="Isaac Sim renderer name")
    parser.add_argument("--camera-eye", type=float, nargs=3, default=None, metavar=("X", "Y", "Z"))
    parser.add_argument("--camera-target", type=float, nargs=3, default=None, metavar=("X", "Y", "Z"))
    parser.add_argument("--prepared-dir", type=Path, default=None, help="Directory for temporary host-rewritten USDA files")
    parser.add_argument("--max-frames", type=int, default=None, help="Exit after N frames; mainly for smoke tests")
    parser.add_argument(
        "--no-physics-inspector-ui",
        action="store_true",
        help="Do not enable the optional PhysX SupportUI extension in GUI mode",
    )
    parser.add_argument("--dry-run", action="store_true", help="Resolve and print scene metadata without starting Isaac Sim")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.expanduser().resolve() if args.repo_root else discover_repo_root()
    config_dir = args.config_dir.expanduser().resolve() if args.config_dir else default_config_dir()
    assets_root = args.assets_root.expanduser().resolve() if args.assets_root else default_assets_root(repo_root)

    selection = load_scene_selection(
        args.config,
        config_dir=config_dir,
        assets_root=assets_root,
        instance_id=args.instance_id,
    )
    if args.dry_run:
        print(json.dumps(selection.to_jsonable(), indent=2, ensure_ascii=False))
        return 0

    reexec_with_isaacsim_numpy_libs()

    return launch_viewer(
        selection,
        repo_root=repo_root,
        assets_root=assets_root,
        headless=args.headless,
        render_mode=args.render_mode,
        camera_eye=args.camera_eye,
        camera_target=args.camera_target,
        prepared_dir=args.prepared_dir,
        max_frames=args.max_frames,
        enable_physics_inspector_ui=not args.no_physics_inspector_ui,
    )


if __name__ == "__main__":
    raise SystemExit(main())
