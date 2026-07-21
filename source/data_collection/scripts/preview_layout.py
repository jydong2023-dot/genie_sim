#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Generate layouts with client/layout and preview them in Isaac Sim.

Does **not** run trajectory collection / recording. Requires a running
data_collection Isaac gRPC server (see --help / docs for how to start it).

Examples
--------
# Layout only (no Isaac)
python scripts/preview_layout.py --layout-only \\
  --task-template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json \\
  --output-dir /home/user/djy/genie_sim/output

# GUI preview (Isaac window stays open; press Enter between instances)
python scripts/preview_layout.py --gui \\
  --task-template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json \\
  --output-dir /home/user/djy/genie_sim/output --num-episodes 2

# Headless: load + save camera PNGs
python scripts/preview_layout.py --headless --save-images \\
  --task-template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json \\
  --output-dir /home/user/djy/genie_sim/output --num-episodes 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client.layout.task_generate import TaskGenerator
from common.base_utils.logger import logger


def _import_isaac_client():
    """Lazy import: pinocchio / gRPC only needed when talking to Isaac."""
    from client.agent.omniagent import DataCollectionAgent
    from client.robot.omni_robot import IsaacSimRpcRobot
    from common.aimdk.protocol.sim import (
        sim_observation_service_pb2,
        sim_observation_service_pb2_grpc,
    )

    return DataCollectionAgent, IsaacSimRpcRobot, sim_observation_service_pb2, sim_observation_service_pb2_grpc

CAMERA_ALIAS = {
    "head_front_Camera": "head",
    "Left_Camera": "left_hand",
    "Right_Camera": "right_hand",
    "head_left_Camera": "head_left",
    "head_right_Camera": "head_right",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--task-template",
        type=Path,
        default=ROOT / "tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json",
        help="data_collection task template JSON",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/home/user/djy/genie_sim/output"),
        help="Where to write generated layout JSONs and preview images",
    )
    p.add_argument("--num-episodes", type=int, default=None, help="Override template num_of_episode")
    p.add_argument("--skip-generate", action="store_true", help="Reuse existing layouts under output-dir/<task>/")
    p.add_argument("--layout-only", action="store_true", help="Only generate layouts; do not connect to Isaac")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--gui", action="store_true", default=False, help="Interactive Isaac GUI preview (default if not --headless)")
    mode.add_argument("--headless", action="store_true", help="Load scenes without waiting for Enter; exit after done")
    p.add_argument("--save-images", action="store_true", help="Capture robot cameras to PNG under output-dir/<task>/preview/")
    p.add_argument(
        "--cameras",
        type=str,
        default="head,left_hand,right_hand",
        help="Comma aliases (head,left_hand,right_hand) mapped from template camera_list",
    )
    p.add_argument("--client-host", type=str, default="localhost:50051")
    p.add_argument(
        "--instance-ids",
        type=str,
        default="",
        help="Comma indices to preview (default: all generated/found)",
    )
    p.add_argument(
        "--keep-absolute-assets",
        action="store_true",
        help="Do not rewrite data_info_dir to paths relative to $SIM_ASSETS (needed for Docker server)",
    )
    return p.parse_args()


def ensure_sim_assets() -> Path:
    root = os.environ.get("SIM_ASSETS")
    if not root:
        try:
            import geniesim_assets

            root = os.path.dirname(geniesim_assets.__file__)
            os.environ["SIM_ASSETS"] = root
        except Exception as e:
            raise RuntimeError(
                "SIM_ASSETS is unset and geniesim_assets is not importable. "
                "export SIM_ASSETS=/path/to/geniesim_assets or pip install -e geniesim_assets"
            ) from e
    path = Path(root).resolve()
    if not path.is_dir():
        raise RuntimeError(f"SIM_ASSETS does not exist: {path}")
    return path


def rewrite_asset_paths_relative(task_info: dict, assets_root: Path) -> dict:
    """Rewrite absolute asset dirs to paths relative to assets_root for the Isaac server."""
    root = str(assets_root.resolve())
    keys = ("data_info_dir", "obj_path", "model_path", "original_model_path")
    for obj in task_info.get("objects", []):
        for key in keys:
            val = obj.get(key)
            if not val or not isinstance(val, str):
                continue
            abs_val = str(Path(val).resolve()) if os.path.isabs(val) else str((assets_root / val).resolve())
            if abs_val == root or abs_val.startswith(root + os.sep):
                obj[key] = os.path.relpath(abs_val, root)
    return task_info


def generate_layouts(template_path: Path, output_dir: Path, num_episodes: int | None) -> tuple[dict, Path, list[Path]]:
    with open(template_path, "r", encoding="utf-8") as f:
        task_info = json.load(f)
    task_name = task_info["task"]
    if num_episodes is None:
        num_episodes = int(task_info.get("recording_setting", {}).get("num_of_episode", 1))
    save_path = output_dir / task_name
    logger.info(f"Generating {num_episodes} layouts -> {save_path}")
    tg = TaskGenerator(task_info)
    tg.generate_tasks(save_path=str(save_path), task_num=num_episodes, task_name=task_name)
    files = sorted(save_path.glob(f"{task_name}_*.json"))
    return task_info, save_path, files


def discover_layouts(template_path: Path, output_dir: Path) -> tuple[dict, Path, list[Path]]:
    with open(template_path, "r", encoding="utf-8") as f:
        task_info = json.load(f)
    task_name = task_info["task"]
    save_path = output_dir / task_name
    files = sorted(save_path.glob(f"{task_name}_*.json"))
    if not files:
        raise FileNotFoundError(f"No layouts in {save_path}; omit --skip-generate first")
    return task_info, save_path, files


def select_files(files: list[Path], instance_ids: str) -> list[Path]:
    if not instance_ids.strip():
        return files
    wanted = {int(x) for x in instance_ids.split(",") if x.strip() != ""}
    selected = []
    for path in files:
        stem = path.stem
        idx_str = stem.rsplit("_", 1)[-1]
        if idx_str.isdigit() and int(idx_str) in wanted:
            selected.append(path)
    if not selected:
        raise ValueError(f"No layouts matched --instance-ids={instance_ids}")
    return selected


def resolve_camera_prims(template: dict, aliases: str) -> list[tuple[str, str]]:
    """Return list of (alias, prim_path) from template recording_setting.camera_list."""
    camera_list = template.get("recording_setting", {}).get("camera_list", [])
    wanted = {a.strip() for a in aliases.split(",") if a.strip()}
    resolved = []
    for prim in camera_list:
        leaf = prim.rstrip("/").split("/")[-1]
        alias = CAMERA_ALIAS.get(leaf, leaf)
        if alias in wanted or leaf in wanted:
            resolved.append((alias, prim))
    if not resolved and camera_list:
        # fallback: first cameras matching common names
        for prim in camera_list:
            leaf = prim.rstrip("/").split("/")[-1]
            alias = CAMERA_ALIAS.get(leaf, leaf)
            if alias in ("head", "left_hand", "right_hand"):
                resolved.append((alias, prim))
    return resolved


def capture_cameras(robot, camera_prims: list[str]) -> list[np.ndarray | None]:
    _, _, sim_observation_service_pb2, sim_observation_service_pb2_grpc = _import_isaac_client()
    stub = sim_observation_service_pb2_grpc.SimObservationServiceStub(robot.client.channel)
    req = sim_observation_service_pb2.GetObservationReq()
    req.isCam = True
    req.CameraReq.render_depth = False
    req.CameraReq.render_semantic = False
    for prim in camera_prims:
        req.CameraReq.camera_prim_list.append(prim)
    rsp = stub.get_observation(req)
    images: list[np.ndarray | None] = []
    for cam in rsp.camera:
        w = int(cam.camera_info.width) or 0
        h = int(cam.camera_info.height) or 0
        raw = cam.rgb_camera.data
        if not raw or w <= 0 or h <= 0:
            images.append(None)
            continue
        arr = np.frombuffer(raw, dtype=np.uint8)
        if arr.size == h * w * 4:
            img = arr.reshape(h, w, 4)[:, :, :3]
        elif arr.size == h * w * 3:
            img = arr.reshape(h, w, 3)
        else:
            logger.warning(f"Unexpected RGB buffer size {arr.size} for {w}x{h}")
            images.append(None)
            continue
        images.append(img.copy())
    return images


def save_preview_images(
    robot,
    cameras: list[tuple[str, str]],
    out_dir: Path,
    instance_stem: str,
) -> dict[str, str]:
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError("opencv-python (cv2) is required for --save-images") from e

    out_dir.mkdir(parents=True, exist_ok=True)
    prims = [p for _, p in cameras]
    images = capture_cameras(robot, prims)
    written = {}
    for (alias, _prim), img in zip(cameras, images):
        if img is None:
            logger.warning(f"No image for camera {alias}")
            continue
        name = f"{alias}.png" if instance_stem.endswith("_0") or instance_stem.endswith("0") else f"{alias}_{instance_stem.rsplit('_', 1)[-1]}.png"
        # Prefer stable names: head.png for id0, head_01.png for id1, ...
        idx = instance_stem.rsplit("_", 1)[-1]
        if idx.isdigit():
            name = f"{alias}.png" if int(idx) == 0 else f"{alias}_{int(idx):02d}.png"
        path = out_dir / name
        bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(path), bgr)
        written[alias] = str(path)
        logger.info(f"Saved {path}")
    return written


def build_robot(template: dict, client_host: str):
    _, IsaacSimRpcRobot, _, _ = _import_isaac_client()
    tg = TaskGenerator(template)
    robot_position = tg.robot_init_pose["position"]
    robot_rotation = tg.robot_init_pose["quaternion"]
    stand = {"stand_type": "cylinder", "stand_size_x": 0.1, "stand_size_y": 0.1}
    if "stand" in template.get("robot", {}):
        stand = template["robot"]["stand"]
    robot_cfg = template["robot"]["robot_cfg"]
    scene_usd = template["scene"]["scene_usd"]
    if isinstance(scene_usd, list):
        scene_usd = scene_usd[0]
    robot_init_arm_pose = template["robot"].get("init_arm_pose")
    robot_init_arm_pose_noise = template["robot"].get("init_arm_pose_noise")
    return IsaacSimRpcRobot(
        robot_cfg=robot_cfg,
        scene_usd=scene_usd,
        client_host=client_host,
        position=robot_position,
        rotation=robot_rotation,
        stand_type=stand["stand_type"],
        stand_size_x=stand["stand_size_x"],
        stand_size_y=stand["stand_size_y"],
        robot_init_arm_pose=robot_init_arm_pose,
        robot_init_arm_pose_noise=robot_init_arm_pose_noise,
    )


def prepare_instance_file(src: Path, assets_root: Path, rewrite: bool) -> Path:
    """Optionally rewrite asset paths; write a temp sibling used for loading."""
    with open(src, "r", encoding="utf-8") as f:
        task_info = json.load(f)
    if rewrite:
        rewrite_asset_paths_relative(task_info, assets_root)
        out = src.with_name(src.stem + "_server.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(task_info, f, indent=2)
        return out
    return src


def preview_instances(
    template: dict,
    files: list[Path],
    *,
    client_host: str,
    gui: bool,
    save_images: bool,
    cameras: list[tuple[str, str]],
    preview_dir: Path,
    assets_root: Path,
    rewrite_assets: bool,
) -> None:
    DataCollectionAgent, _, _, _ = _import_isaac_client()
    logger.info(f"Connecting to Isaac server at {client_host}")
    robot = build_robot(template, client_host)
    agent = DataCollectionAgent(robot)

    try:
        for i, path in enumerate(files):
            load_path = prepare_instance_file(path, assets_root, rewrite_assets)
            logger.info(f"[{i+1}/{len(files)}] Loading layout {path.name}")
            agent.reset()
            time.sleep(0.5)
            agent.generate_layout(str(load_path))
            try:
                robot.open_gripper(id="right", detach=False)
                robot.open_gripper(id="left", detach=False)
            except Exception as e:
                logger.warning(f"open_gripper skipped: {e}")
            time.sleep(1.0)

            if save_images and cameras:
                save_preview_images(robot, cameras, preview_dir, path.stem)

            if gui:
                print(
                    f"\n=== Preview ready: {path.name} ===\n"
                    f"Inspect the Isaac Sim window, then press Enter for next "
                    f"(or Ctrl-C to stop)...",
                    flush=True,
                )
                try:
                    input()
                except EOFError:
                    break
            else:
                logger.info(f"Headless preview done for {path.name}")
    finally:
        try:
            robot.client.exit()
        except Exception:
            pass


def main() -> int:
    args = parse_args()
    assets_root = ensure_sim_assets()
    template_path = args.task_template.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.gui and not args.headless and not args.layout_only:
        args.gui = True  # default interactive

    if args.skip_generate:
        template, save_path, files = discover_layouts(template_path, output_dir)
    else:
        template, save_path, files = generate_layouts(template_path, output_dir, args.num_episodes)

    files = select_files(files, args.instance_ids)
    logger.info(f"Layouts ({len(files)}): {[p.name for p in files]}")

    if args.layout_only:
        print(f"Layout-only done. Saved under {save_path}")
        return 0

    cameras = resolve_camera_prims(template, args.cameras)
    if args.save_images and not cameras:
        logger.warning("No cameras resolved from template; --save-images will be skipped")

    preview_dir = save_path / "preview"
    preview_instances(
        template,
        files,
        client_host=args.client_host,
        gui=bool(args.gui and not args.headless),
        save_images=args.save_images or args.headless,
        cameras=cameras,
        preview_dir=preview_dir,
        assets_root=assets_root,
        rewrite_assets=not args.keep_absolute_assets,
    )
    print(f"Done. Layouts: {save_path}")
    if args.save_images or args.headless:
        print(f"Preview images: {preview_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
