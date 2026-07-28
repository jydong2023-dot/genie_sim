#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Run the 10 G2 first-run demo tasks until each collects N successful trajectories.

Prerequisites (inside the data_collection Docker container):
  Terminal 1:
    /isaac-sim/python.sh scripts/data_collector_server.py \\
      --enable_physics --enable_curobo --publish_ros

  Terminal 2:
    /isaac-sim/python.sh scripts/run_first_run_demos.py --use-recording

See README_DEMO.md for the task list and difficulty ordering.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.first_run_demo_tasks import (  # noqa: E402
    FIRST_RUN_DEMOS,
    episode_success,
    find_new_recording_dir,
    parse_index_selection,
    snapshot_recording_dirs,
)


@dataclass
class AttemptResult:
    attempt: int
    success: bool
    recording_dir: str | None = None
    task_result_path: str | None = None
    metric_status: str | None = None
    error: str | None = None


@dataclass
class TaskRunResult:
    index: str
    label: str
    template: str
    task_id: str
    target_successes: int
    successes: int = 0
    attempts: int = 0
    success_dirs: list[str] = field(default_factory=list)
    attempt_log: list[AttemptResult] = field(default_factory=list)
    status: str = "pending"  # pending | completed | partial | failed


def close_client_channel(robot) -> None:
    channel = getattr(getattr(robot, "client", None), "channel", None)
    if channel is not None:
        channel.close()


def wait_for_task_result(recording_dir: Path, timeout: float, poll_interval: float = 1.0) -> tuple[bool, dict[str, Any] | None]:
    deadline = time.monotonic() + timeout
    task_result_path = recording_dir / "task_result.json"
    extract_log_path = recording_dir / "extract.log"
    while time.monotonic() < deadline:
        ok, task_result = episode_success(recording_dir)
        if task_result is not None:
            return ok, task_result
        if not recording_dir.exists():
            return False, None
        if extract_log_path.is_file():
            extract_log = extract_log_path.read_text(encoding="utf-8", errors="replace")
            if "Error in extracting data" in extract_log:
                return False, {"metric_status": f"extract_failed:{extract_log_path}"}
        time.sleep(poll_interval)
    ok, task_result = episode_success(recording_dir)
    if task_result is not None:
        return ok, task_result
    return False, {"metric_status": f"task_result_timeout:{task_result_path}"}


def configure_seed(seed: int | None) -> None:
    if seed is None:
        return

    import random

    import numpy as np

    random.seed(seed)
    np.random.seed(seed)


def parse_template_overrides(raw_overrides: list[str] | None) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for raw in raw_overrides or []:
        if "=" not in raw:
            raise ValueError(f"Invalid --template-override {raw!r}; expected INDEX=PATH")
        index, template = raw.split("=", 1)
        index = index.strip()
        template = template.strip()
        if not index or not template:
            raise ValueError(f"Invalid --template-override {raw!r}; expected INDEX=PATH")
        overrides[index] = template
    return overrides


def apply_template_overrides(demos: list[dict[str, str]], overrides: dict[str, str]) -> list[dict[str, str]]:
    updated: list[dict[str, str]] = []
    known = {demo["index"] for demo in demos}
    unknown = sorted(set(overrides) - known, key=int)
    if unknown:
        raise ValueError(f"Template override index out of selected range: {unknown}")
    for demo in demos:
        item = dict(demo)
        if item["index"] in overrides:
            item["template"] = overrides[item["index"]]
        updated.append(item)
    return updated


def wait_for_server(client_host: str, timeout: float) -> None:
    import grpc

    channel = None
    try:
        channel = grpc.insecure_channel(client_host)
        grpc.channel_ready_future(channel).result(timeout=timeout)
    except (grpc.FutureTimeoutError, grpc.RpcError, OSError) as exc:
        raise RuntimeError(
            f"Cannot connect to gRPC server at {client_host}. "
            "Start Terminal 1 with: /isaac-sim/python.sh scripts/data_collector_server.py "
            "--enable_physics --enable_curobo --publish_ros"
        ) from exc
    finally:
        if channel is not None:
            channel.close()


def build_robot(task_info: dict[str, Any], client_host: str, connect_timeout: float | None):
    from client.layout.task_generate import TaskGenerator
    from client.robot.omni_robot import IsaacSimRpcRobot

    task_generator = TaskGenerator(task_info)
    stand = {"stand_type": "cylinder", "stand_size_x": 0.1, "stand_size_y": 0.1}
    robot_init_arm_pose = None
    robot_init_arm_pose_noise = None
    robot_cfg = task_info["robot"]["robot_cfg"]
    if "stand" in task_info["robot"]:
        stand = task_info["robot"]["stand"]
    if "init_arm_pose" in task_info["robot"]:
        robot_init_arm_pose = task_info["robot"]["init_arm_pose"]
    if "init_arm_pose_noise" in task_info["robot"]:
        robot_init_arm_pose_noise = task_info["robot"]["init_arm_pose_noise"]

    return IsaacSimRpcRobot(
        robot_cfg=robot_cfg,
        scene_usd=task_info["scene"]["scene_usd"],
        client_host=client_host,
        position=task_generator.robot_init_pose["position"],
        rotation=task_generator.robot_init_pose["quaternion"],
        stand_type=stand["stand_type"],
        stand_size_x=stand["stand_size_x"],
        stand_size_y=stand["stand_size_y"],
        robot_init_arm_pose=robot_init_arm_pose,
        robot_init_arm_pose_noise=robot_init_arm_pose_noise,
        connect_timeout=connect_timeout,
    ), task_generator


def run_single_episode(agent, task_generator, task_info, task_folder, use_recording) -> None:
    task_name = task_info["task"]
    shutil.rmtree(task_folder, ignore_errors=True)
    task_folder.mkdir(parents=True, exist_ok=True)
    task_generator.generate_tasks(
        save_path=str(task_folder),
        task_num=1,
        task_name=task_name,
    )

    render_semantic = task_info.get("recording_setting", {}).get("render_semantic", False)
    agent.run(
        task_folder=str(task_folder),
        camera_list=task_info["recording_setting"]["camera_list"],
        use_recording=use_recording,
        workspaces=task_generator.workspaces_in_world_frame,
        fps=task_info["recording_setting"]["fps"],
        render_semantic=render_semantic,
        origin_task_info=task_info,
    )


def run_task_until_successes(
    demo: dict[str, str],
    *,
    root: Path,
    target_successes: int,
    max_attempts: int,
    client_host: str,
    connect_timeout: float | None,
    use_recording: bool,
    prune_failed: bool,
    saved_task_root: Path,
    result_timeout: float,
) -> TaskRunResult:
    from client.agent.omniagent import DataCollectionAgent
    from common.base_utils.logger import logger

    template_path = root / demo["template"]
    if not template_path.is_file():
        raise FileNotFoundError(f"Task template not found: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        task_info = json.load(f)

    task_id = task_info["task"]
    result = TaskRunResult(
        index=demo["index"],
        label=demo["label"],
        template=demo["template"],
        task_id=task_id,
        target_successes=target_successes,
    )

    robot, task_generator = build_robot(task_info, client_host, connect_timeout)
    agent = DataCollectionAgent(robot)
    task_folder = saved_task_root / task_id

    try:
        while result.successes < target_successes and result.attempts < max_attempts:
            result.attempts += 1
            before_dirs = snapshot_recording_dirs(root)
            attempt = AttemptResult(attempt=result.attempts, success=False)

            try:
                run_single_episode(agent, task_generator, task_info, task_folder, use_recording)
                time.sleep(1.0)
                new_dir = find_new_recording_dir(root, before_dirs)
                if new_dir is None:
                    attempt.error = "No new recording_data directory detected"
                else:
                    attempt.recording_dir = str(new_dir)
                    attempt.task_result_path = str(new_dir / "task_result.json")
                    ok, task_result = wait_for_task_result(new_dir, result_timeout)
                    attempt.success = ok
                    attempt.metric_status = (task_result or {}).get("metric_status")
                    if ok:
                        result.successes += 1
                        result.success_dirs.append(str(new_dir))
                        logger.info(
                            "Task %s success %d/%d -> %s",
                            task_id,
                            result.successes,
                            target_successes,
                            new_dir.name,
                        )
                    elif prune_failed:
                        shutil.rmtree(new_dir, ignore_errors=True)
                        attempt.recording_dir = None
                        attempt.task_result_path = None
            except Exception as exc:
                attempt.error = str(exc)
                logger.exception("Attempt %d failed for %s", result.attempts, task_id)

            result.attempt_log.append(attempt)

        if result.successes >= target_successes:
            result.status = "completed"
        elif result.successes > 0:
            result.status = "partial"
        else:
            result.status = "failed"
    finally:
        try:
            close_client_channel(robot)
        except Exception:
            logger.warning("Closing client channel failed for task %s", task_id)

    return result


def write_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect successful trajectories for the 10 G2 first-run demo tasks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--target-successes", type=int, default=2)
    parser.add_argument("--max-attempts-per-task", type=int, default=30)
    parser.add_argument("--tasks", type=str, default=None, help="e.g. '1,3,8' or '1-5'")
    parser.add_argument(
        "--template-override",
        action="append",
        default=[],
        metavar="INDEX=PATH",
        help="Override a selected demo task template, e.g. 3=tasks/overrides/pick_stationery.json",
    )
    parser.add_argument("--client-host", type=str, default="localhost:50051")
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=None, help="Seed Python and NumPy task-generation randomness")
    parser.add_argument(
        "--result-timeout",
        type=float,
        default=600.0,
        help="Seconds to wait for async extraction to write task_result.json",
    )
    parser.add_argument("--use-recording", action="store_true", default=False)
    parser.add_argument(
        "--keep-failed",
        action="store_true",
        help="Keep failed episode recordings (default: delete failed episodes to save disk)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "logs" / "first_run_demos" / "manifest.json",
    )
    parser.add_argument(
        "--saved-task-root",
        type=Path,
        default=ROOT / "saved_task" / "first_run_demos",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.target_successes < 1:
        raise SystemExit("--target-successes must be >= 1")
    if args.max_attempts_per_task < args.target_successes:
        raise SystemExit("--max-attempts-per-task must be >= --target-successes")

    configure_seed(args.seed)

    selected = parse_index_selection(args.tasks, len(FIRST_RUN_DEMOS))
    demos = [d for d in FIRST_RUN_DEMOS if int(d["index"]) in selected]
    template_overrides = parse_template_overrides(args.template_override)
    demos = apply_template_overrides(demos, template_overrides)
    prune_failed = not args.keep_failed

    if args.dry_run:
        print(f"Would run {len(demos)} task(s); target {args.target_successes} success(es) each")
        for demo in demos:
            print(f"  [{demo['index']}] {demo['label']} -> {demo['template']}")
        return 0

    os.chdir(ROOT)
    wait_for_server(args.client_host, args.connect_timeout)

    started_at = datetime.now(timezone.utc).isoformat()
    task_results: list[TaskRunResult] = []

    for demo in demos:
        from common.base_utils.logger import logger

        logger.info(
            "=== Demo [%s] %s (need %d successes, max %d attempts) ===",
            demo["index"],
            demo["label"],
            args.target_successes,
            args.max_attempts_per_task,
        )
        task_results.append(
            run_task_until_successes(
                demo,
                root=ROOT,
                target_successes=args.target_successes,
                max_attempts=args.max_attempts_per_task,
                client_host=args.client_host,
                connect_timeout=args.connect_timeout,
                use_recording=args.use_recording,
                prune_failed=prune_failed,
                saved_task_root=args.saved_task_root,
                result_timeout=args.result_timeout,
            )
        )

    completed = sum(1 for r in task_results if r.status == "completed")
    manifest = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "target_successes_per_task": args.target_successes,
        "max_attempts_per_task": args.max_attempts_per_task,
        "result_timeout": args.result_timeout,
        "prune_failed": prune_failed,
        "tasks_requested": len(demos),
        "tasks_completed": completed,
        "tasks": [asdict(r) for r in task_results],
    }
    write_manifest(args.manifest, manifest)

    print("\n=== First-run demo batch summary ===")
    for r in task_results:
        print(
            f"[{r.index}] {r.label}: {r.successes}/{r.target_successes} successes "
            f"in {r.attempts} attempts ({r.status})"
        )
        for d in r.success_dirs:
            print(f"      ✓ {d}")
    print(f"\nManifest: {args.manifest}")

    return 0 if completed == len(demos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
