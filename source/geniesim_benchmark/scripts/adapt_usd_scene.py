#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Generate a debug benchmark YAML and eval-task JSON for an existing USD scene."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


USD_SUFFIXES = {".usd", ".usda", ".usdc"}
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = PACKAGE_ROOT / "src" / "geniesim_benchmark"
DEFAULT_CONFIG_DIR = PACKAGE_SRC / "config"
DEFAULT_EVAL_TASK_DIR = PACKAGE_SRC / "benchmark" / "config" / "eval_tasks"
DEFAULT_ROBOT_CONFIG_DIR = PACKAGE_SRC / "app" / "robot_cfg"


def slugify(value: str) -> str:
    """Convert a path/name into a benchmark-safe identifier."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    if not slug:
        raise ValueError(f"cannot derive a valid identifier from {value!r}")
    return slug


def infer_assets_root(scene_usd: Path, explicit_root: Path | None = None) -> Path:
    """Resolve the assets root and prove that the scene is contained by it."""
    scene_usd = scene_usd.expanduser().resolve()
    candidates: list[Path] = []
    if explicit_root is not None:
        candidates.append(explicit_root.expanduser().resolve())
    sim_assets = os.environ.get("SIM_ASSETS")
    if sim_assets:
        candidates.append(Path(sim_assets).expanduser().resolve())
    candidates.extend(parent for parent in scene_usd.parents if parent.name == "geniesim_assets")

    for candidate in candidates:
        try:
            scene_usd.relative_to(candidate)
        except ValueError:
            continue
        if candidate.is_dir():
            return candidate

    raise ValueError(
        f"scene is not under a detectable GenieSim assets root: {scene_usd}. "
        "Pass --assets-root explicitly."
    )


def validate_scene(scene_usd: Path, assets_root: Path) -> Path:
    scene_usd = scene_usd.expanduser().resolve()
    if not scene_usd.is_file():
        raise FileNotFoundError(f"scene USD does not exist: {scene_usd}")
    if scene_usd.suffix.lower() not in USD_SUFFIXES:
        raise ValueError(f"scene must be .usd, .usda, or .usdc: {scene_usd}")
    try:
        return scene_usd.relative_to(assets_root)
    except ValueError as exc:
        raise ValueError(f"scene must be inside assets root {assets_root}: {scene_usd}") from exc


def load_robot_config(robot_cfg: str, robot_config_dir: Path) -> dict[str, Any]:
    robot_cfg_path = robot_config_dir / robot_cfg
    if not robot_cfg_path.is_file():
        raise FileNotFoundError(f"robot config does not exist: {robot_cfg_path}")
    with robot_cfg_path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data.get("robot"), dict):
        raise ValueError(f"robot config has no 'robot' object: {robot_cfg_path}")
    if not isinstance(data.get("camera"), dict) or not data["camera"]:
        raise ValueError(f"robot config has no cameras: {robot_cfg_path}")
    return data


def resolve_cameras(robot_config: dict[str, Any], requested: list[str] | None) -> list[str]:
    configured = list(robot_config["camera"])
    cameras = requested or configured
    unknown = [camera for camera in cameras if camera not in robot_config["camera"]]
    if unknown:
        raise ValueError(
            "camera paths are missing from the robot config: " + ", ".join(unknown)
        )
    return cameras


def _asset_config_path(relative_path: Path) -> str:
    return "/" + relative_path.as_posix().lstrip("/")


def _scene_name(relative_scene: Path) -> str:
    parts = list(relative_scene.with_suffix("").parts)
    if parts and parts[0] == "background":
        parts = parts[1:]
    return "/".join(parts)


def _scene_identifier(relative_scene: Path, workspace_id: str) -> str:
    return f"{_scene_name(relative_scene)}/{workspace_id}"


def build_configs(
    *,
    relative_scene: Path,
    task_name: str,
    task_type: str,
    platform: str,
    robot_id: str,
    robot_cfg: str,
    robot_arm: str,
    cameras: list[str],
    workspace_id: str,
    robot_position: list[float],
    robot_quaternion: list[float],
    workspace_position: list[float],
    workspace_quaternion: list[float],
    workspace_size: list[float],
    base_task: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the two config documents while preserving their shared invariants."""
    scene_usd = _asset_config_path(relative_scene)
    scene_info_dir = _asset_config_path(relative_scene.parent) + "/"
    scene_id = _scene_identifier(relative_scene, workspace_id)

    run_config = {
        "app": {"enable_rate_limit": True, "enable_ros": False},
        "benchmark": {
            "task_name": task_name,
            "platform": platform,
            "sub_task_name": "",
            "seed": 1,
            "model_arc": "pi",
            "policy_class": "DemoPolicy",
            "env_class": "DummyEnv",
            "num_episode": 1,
            "num_instances": 1,
            "preview": True,
            "record": False,
            "keep_open": True,
        },
    }
    eval_task = {
        "generalization": {"material": {"enable": False, "num": 0}},
        "objects": {
            "constraints": None,
            "extra_objects": [],
            "fix_objects": [],
            "task_related_objects": [],
        },
        "problem_instance": 0,
        "recording_setting": {
            "camera_list": cameras,
            "fps": 30,
            "num_of_episode": 1,
        },
        "robot": {
            "arm": robot_arm,
            "robot_cfg": robot_cfg,
            "robot_id": robot_id,
            "robot_init_pose": {
                workspace_id: {
                    "position": robot_position,
                    "quaternion": robot_quaternion,
                }
            },
        },
        "scene": {
            "function_space_objects": {
                workspace_id: {
                    "material_obj_prim": {},
                    "position": workspace_position,
                    "quaternion": workspace_quaternion,
                    "size": workspace_size,
                }
            },
            "scene_id": scene_id,
            "scene_info_dir": scene_info_dir,
            "scene_usd": scene_usd,
        },
        "stages": [
            {
                "action": "pick",
                "active": {"object_id": "gripper", "primitive": None},
                "extra_params": {"pick_up_direction": "x", "pick_up_distance": 0.12},
                "passive": {"object_id": "", "primitive": None},
            }
        ],
        "task": base_task,
        "task_subtype": "debug",
        "task_type": task_type,
    }
    return run_config, eval_task


def validate_generated_configs(run_config: dict[str, Any], eval_task: dict[str, Any]) -> None:
    task_name = run_config["benchmark"]["task_name"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", task_name):
        raise ValueError(f"task name must contain only letters, digits, and underscores: {task_name}")

    scene = eval_task["scene"]
    workspace_id = scene["scene_id"].split("/")[-1]
    if workspace_id not in scene["function_space_objects"]:
        raise ValueError("scene_id suffix does not match function_space_objects")
    if workspace_id not in eval_task["robot"]["robot_init_pose"]:
        raise ValueError("scene_id suffix does not match robot_init_pose")
    if not scene["scene_usd"].startswith("/"):
        raise ValueError("scene_usd must be assets-root-relative and start with '/'")


def _stage_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        stream.write(text)
        return Path(stream.name)


def write_outputs(outputs: dict[Path, str], *, force: bool) -> None:
    existing = [path for path in outputs if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "refusing to overwrite existing files; pass --force: "
            + ", ".join(str(path) for path in existing)
        )

    staged: dict[Path, Path] = {}
    try:
        for destination, content in outputs.items():
            staged[destination] = _stage_text(destination, content)
        for destination, temporary in staged.items():
            temporary.replace(destination)
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-usd", type=Path, required=True, help="Existing USD scene inside assets root.")
    parser.add_argument(
        "--assets-root",
        type=Path,
        help="Assets root; inferred from a geniesim_assets ancestor by default.",
    )
    parser.add_argument("--robot-id", default="dual_agx_nero")
    parser.add_argument("--robot-cfg", default="dual_agx_nero.json")
    parser.add_argument("--platform", help="Benchmark platform (default: --robot-id).")
    parser.add_argument("--robot-arm", help="Arm mode (default: value from robot config).")
    parser.add_argument(
        "--camera",
        action="append",
        help="Camera prim path; repeat to override the robot-config camera list.",
    )
    parser.add_argument("--task-name", help="Eval-task ID and JSON filename; auto-generated by default.")
    parser.add_argument("--config-name", help="Run YAML filename with or without .yaml; auto-generated by default.")
    parser.add_argument("--task-type", help="Eval task_type; auto-generated by default.")
    parser.add_argument("--base-task", default="table_task_1_g2_op", help="Existing task generator template to reuse.")
    parser.add_argument("--workspace-id", default="workspace_00")
    parser.add_argument("--robot-position", nargs=3, type=float, default=[-0.71, 0.0, 0.0], metavar=("X", "Y", "Z"))
    parser.add_argument(
        "--robot-quaternion",
        nargs=4,
        type=float,
        default=[1.0, 0.0, 0.0, 0.0],
        metavar=("W", "X", "Y", "Z"),
    )
    parser.add_argument("--workspace-position", nargs=3, type=float, default=[0.0, 0.0, 0.75], metavar=("X", "Y", "Z"))
    parser.add_argument(
        "--workspace-quaternion",
        nargs=4,
        type=float,
        default=[1.0, 0.0, 0.0, 0.0],
        metavar=("W", "X", "Y", "Z"),
    )
    parser.add_argument("--workspace-size", nargs=3, type=float, default=[0.0, 0.0, 0.0], metavar=("X", "Y", "Z"))
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--eval-task-dir", type=Path, default=DEFAULT_EVAL_TASK_DIR)
    parser.add_argument("--robot-config-dir", type=Path, default=DEFAULT_ROBOT_CONFIG_DIR)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print generated documents without writing files.",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing generated YAML/JSON files.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scene_usd = args.scene_usd.expanduser().resolve()
    assets_root = infer_assets_root(scene_usd, args.assets_root)
    relative_scene = validate_scene(scene_usd, assets_root)
    robot_config = load_robot_config(args.robot_cfg, args.robot_config_dir.expanduser().resolve())
    cameras = resolve_cameras(robot_config, args.camera)

    scene_slug = slugify(_scene_name(relative_scene))
    task_name = args.task_name or f"table_task_{slugify(args.robot_id)}_{scene_slug}"
    config_stem = (
        slugify(args.config_name.removesuffix(".yaml"))
        if args.config_name
        else f"{slugify(args.robot_id)}_{scene_slug}_debug"
    )
    task_type = args.task_type or f"{scene_slug}_debug"
    robot_arm = args.robot_arm or str(robot_config["robot"].get("arm", "dual"))

    run_config, eval_task = build_configs(
        relative_scene=relative_scene,
        task_name=task_name,
        task_type=task_type,
        platform=args.platform or args.robot_id,
        robot_id=args.robot_id,
        robot_cfg=args.robot_cfg,
        robot_arm=robot_arm,
        cameras=cameras,
        workspace_id=slugify(args.workspace_id),
        robot_position=args.robot_position,
        robot_quaternion=args.robot_quaternion,
        workspace_position=args.workspace_position,
        workspace_quaternion=args.workspace_quaternion,
        workspace_size=args.workspace_size,
        base_task=args.base_task,
    )
    validate_generated_configs(run_config, eval_task)

    yaml_text = yaml.safe_dump(run_config, sort_keys=False, allow_unicode=False)
    json_text = json.dumps(eval_task, indent=2, ensure_ascii=True) + "\n"
    config_path = args.config_dir.expanduser().resolve() / f"{config_stem}.yaml"
    eval_task_path = args.eval_task_dir.expanduser().resolve() / f"{task_name}.json"

    if args.dry_run:
        print(f"# YAML: {config_path}")
        print(yaml_text.rstrip())
        print(f"\n# JSON: {eval_task_path}")
        print(json_text.rstrip())
        return 0

    write_outputs({config_path: yaml_text, eval_task_path: json_text}, force=args.force)
    print(f"Generated benchmark YAML: {config_path}")
    print(f"Generated eval-task JSON: {eval_task_path}")
    print("Run in the GenieSim container:")
    print(
        f"  geniesim benchmark run {config_path.name} --app.headless=false "
        "--benchmark.keep_open=true --benchmark.record=false"
    )
    print("This is a scene/robot debug adapter; target-object physics and success scoring are not generated.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, FileExistsError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
