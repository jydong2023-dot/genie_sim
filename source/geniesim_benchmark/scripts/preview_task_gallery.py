#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Generate a preview gallery for benchmark task configs.

This script is intentionally a batch orchestrator around the existing benchmark
preview path. Each config is launched in a separate process with
``--benchmark.preview=true`` so Isaac Sim can load the robot, scene, and first
instruction, save the three policy camera images, then exit without contacting
an inference server.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
STANDALONE_SRC = SCRIPT_DIR.parents[1] / "scene_augmentation" / "src"
if STANDALONE_SRC.is_dir() and str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from scene_augmentation import build_contact_sheet  # noqa: E402

SKIP_CONFIG_NAMES = frozenset({"config.yaml", "template.yaml", "teleop.yaml"})
CAMERA_SUFFIXES = {
    "_head.png": "head",
    "_left_hand.png": "left_hand",
    "_right_hand.png": "right_hand",
}


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_config_dir() -> Path:
    return package_root() / "src" / "geniesim_benchmark" / "config"


def discover_repo_root(start: Path | None = None) -> Path:
    """Walk upward to the checkout root, falling back to the package parent."""
    env_root = os.environ.get("GENIESIM_REPO_ROOT") or os.environ.get("SIM_REPO_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "source" / "geniesim_benchmark").is_dir() and (candidate / "VERSION").is_file():
            return candidate
    return package_root().parent.parent.parent.parent.resolve()


def iter_task_configs(
    config_dir: Path,
    *,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
    limit: int | None = None,
) -> list[Path]:
    """Return runnable benchmark YAML configs in deterministic order."""
    include_terms = tuple(s.lower() for s in include if s)
    exclude_terms = tuple(s.lower() for s in exclude if s)
    configs: list[Path] = []
    for path in sorted(config_dir.glob("*.yaml")):
        name = path.name
        stem_lower = path.stem.lower()
        if name in SKIP_CONFIG_NAMES or name.startswith("_"):
            continue
        if include_terms and not any(term in stem_lower for term in include_terms):
            continue
        if exclude_terms and any(term in stem_lower for term in exclude_terms):
            continue
        configs.append(path.resolve())
        if limit is not None and len(configs) >= limit:
            break
    return configs


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return data or {}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load_metadata(config_path: Path, config_dir: Path) -> dict:
    """Read cheap task metadata without importing the heavy benchmark runtime."""
    config = _read_yaml(config_path)
    benchmark_cfg = config.get("benchmark", {}) or {}
    task_name = benchmark_cfg.get("task_name", "")
    sub_task_name = benchmark_cfg.get("sub_task_name", "")

    package_dir = config_dir.resolve().parent
    eval_task = _read_json(package_dir / "benchmark" / "config" / "eval_tasks" / f"{task_name}.json")
    robot = eval_task.get("robot", {}) or {}
    scene = eval_task.get("scene", {}) or {}

    return {
        "config_name": config_path.stem,
        "config_path": str(config_path),
        "task_name": task_name,
        "sub_task_name": sub_task_name,
        "model_arc": benchmark_cfg.get("model_arc", ""),
        "robot_cfg": robot.get("robot_cfg", ""),
        "robot_id": robot.get("robot_id", ""),
        "scene_usd": scene.get("scene_usd", ""),
        "scene_id": scene.get("scene_id", ""),
    }


def build_preview_command(
    config_path: Path,
    *,
    geniesim_bin: str,
    task_output_dir: Path,
    num_instances: int = 1,
    instance_ids: Iterable[int] = (),
) -> list[str]:
    """Command that launches one fast, headless preview run."""
    exact_ids = tuple(int(value) for value in instance_ids)
    command = [
        geniesim_bin,
        "benchmark",
        "run",
        str(config_path),
        "--app.headless=true",
        "--benchmark.preview=true",
        "--benchmark.num_episode=1",
        f"--benchmark.num_instances={num_instances}",
        "--benchmark.enable_vec=0",
        "--benchmark.record=false",
        f"--benchmark.output_dir={task_output_dir}",
    ]
    if exact_ids:
        command.append(
            "--benchmark.instance_ids=" + ",".join(str(value) for value in exact_ids)
        )
    return command


def build_child_env(repo_root: Path) -> dict[str, str]:
    """Environment for the system-Python geniesim child process."""
    env = os.environ.copy()
    # /isaac-sim/python.sh exports Kit Python 3.11 paths. The geniesim CLI may
    # run under system Python 3.12, so inheriting them causes stdlib ABI mismatches.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.setdefault("GENIESIM_SKIP_AUTOBOOT", "1")
    env["GENIESIM_REPO_ROOT"] = str(repo_root)
    env["SIM_REPO_ROOT"] = str(repo_root)
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def snapshot_preview_images(debug_dir: Path) -> set[Path]:
    if not debug_dir.is_dir():
        return set()
    return {p.resolve() for p in debug_dir.glob("preview_*.png") if p.is_file()}


def _camera_name(path: Path) -> str | None:
    name = path.name
    for suffix, camera in CAMERA_SUFFIXES.items():
        if name.endswith(suffix):
            return camera
    return None


def archive_new_preview_images(
    debug_dir: Path,
    before: set[Path],
    task_dir: Path,
    instance_ids: Iterable[int] = (),
) -> dict[str, str]:
    """Move newly-created preview images into ``task_dir`` with stable names."""
    task_dir.mkdir(parents=True, exist_ok=True)
    after = snapshot_preview_images(debug_dir)
    new_files = sorted(after - before, key=lambda p: p.stat().st_mtime_ns)
    archived: dict[str, str] = {}
    exact_ids = tuple(sorted(int(value) for value in instance_ids))
    if exact_ids:
        grouped = {
            camera: sorted(
                (path for path in new_files if _camera_name(path) == camera),
                key=lambda path: path.name,
            )
            for camera in CAMERA_SUFFIXES.values()
        }
        for camera, paths in grouped.items():
            for instance_id, src in zip(exact_ids, paths):
                instance_dir = task_dir / str(instance_id)
                instance_dir.mkdir(parents=True, exist_ok=True)
                dst = instance_dir / f"{camera}.png"
                if dst.exists():
                    dst.unlink()
                shutil.move(str(src), str(dst))
                archived[f"{instance_id}/{camera}"] = str(dst)
        return archived

    counts: dict[str, int] = {}
    for src in new_files:
        camera = _camera_name(src)
        if camera is None:
            continue
        idx = counts.get(camera, 0)
        counts[camera] = idx + 1
        dst_name = f"{camera}.png" if idx == 0 else f"{camera}_{idx:02d}.png"
        dst = task_dir / dst_name
        if dst.exists():
            dst.unlink()
        shutil.move(str(src), str(dst))
        archived[camera if idx == 0 else f"{camera}_{idx:02d}"] = str(dst)
    return archived


def find_task_configs(config_dir: Path, sub_task_name: str) -> list[Path]:
    """Find benchmark YAMLs that retain the requested sub-task name."""
    matches = []
    for path in iter_task_configs(config_dir):
        benchmark = (_read_yaml(path).get("benchmark", {}) or {})
        if benchmark.get("sub_task_name") == sub_task_name:
            matches.append(path)
    return matches


def write_index(output_dir: Path, rows: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fieldnames = [
        "config_name",
        "task_name",
        "sub_task_name",
        "robot_cfg",
        "robot_id",
        "scene_usd",
        "scene_id",
        "exit_code",
        "status",
        "task_dir",
    ]
    with (output_dir / "index.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _task_done(task_dir: Path) -> bool:
    metadata_path = task_dir / "metadata.json"
    if not metadata_path.is_file():
        return False
    metadata = _read_json(metadata_path)
    images = metadata.get("images", {}) or {}
    return metadata.get("status") == "ok" and all(Path(p).is_file() for p in images.values())


def run_one_config(
    config_path: Path,
    *,
    config_dir: Path,
    output_dir: Path,
    debug_dir: Path,
    repo_root: Path,
    geniesim_bin: str,
    num_instances: int = 1,
    instance_ids: Iterable[int] = (),
    dry_run: bool = False,
) -> dict:
    task_dir = output_dir / config_path.stem
    task_dir.mkdir(parents=True, exist_ok=True)

    metadata = load_metadata(config_path, config_dir)
    metadata["task_dir"] = str(task_dir)
    metadata["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    exact_ids = tuple(sorted(int(value) for value in instance_ids))
    cmd = build_preview_command(
        config_path,
        geniesim_bin=geniesim_bin,
        task_output_dir=task_dir / "eval",
        num_instances=num_instances,
        instance_ids=exact_ids,
    )
    metadata["command"] = cmd
    metadata["num_instances"] = num_instances
    metadata["instance_ids"] = list(exact_ids)

    before = snapshot_preview_images(debug_dir)
    if dry_run:
        metadata.update({"exit_code": 0, "status": "dry-run", "images": {}})
        (task_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return metadata

    proc = subprocess.run(cmd, env=build_child_env(repo_root))
    images = archive_new_preview_images(
        debug_dir, before, task_dir, instance_ids=exact_ids
    )
    expected_images = len(exact_ids) * len(CAMERA_SUFFIXES) if exact_ids else 1
    metadata.update(
        {
            "exit_code": proc.returncode,
            "status": "ok" if proc.returncode == 0 and len(images) >= expected_images else "failed",
            "images": images,
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    (task_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metadata


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=default_config_dir(), help="Directory containing task YAMLs")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory where the gallery will be written")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repo root used for SIM_REPO_ROOT/debug_preview")
    parser.add_argument("--debug-dir", type=Path, default=None, help="Override existing preview image directory")
    parser.add_argument(
        "--geniesim-bin",
        default=os.environ.get("GENIESIM_BIN", "geniesim"),
        help="geniesim executable",
    )
    parser.add_argument(
        "--instance-ids",
        default="",
        help="Exact comma-separated numeric scene IDs (overrides count sampling).",
    )
    parser.add_argument("--include", action="append", default=[], help="Only run configs whose stem contains this text")
    parser.add_argument("--exclude", action="append", default=[], help="Skip configs whose stem contains this text")
    parser.add_argument("--limit", type=int, default=None, help="Run at most N configs after filtering")
    parser.add_argument(
        "--num-instances",
        type=int,
        default=1,
        help="Number of numeric subtask instances per config; 0 selects all",
    )
    parser.add_argument("--resume", action="store_true", help="Skip task dirs that already contain successful metadata")
    parser.add_argument("--dry-run", action="store_true", help="Write metadata/index without launching Isaac Sim")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed preview")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_dir = args.config_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    repo_root = args.repo_root.expanduser().resolve() if args.repo_root else discover_repo_root()
    debug_dir = args.debug_dir.expanduser().resolve() if args.debug_dir else repo_root / "debug_preview"

    configs = iter_task_configs(config_dir, include=args.include, exclude=args.exclude, limit=args.limit)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    failures = 0
    instance_ids = tuple(
        int(value.strip()) for value in args.instance_ids.split(",") if value.strip()
    )

    print(f"Preview gallery output: {output_dir}")
    print(f"Task configs: {len(configs)}")
    print(f"debug_preview: {debug_dir}")
    print()

    for idx, config_path in enumerate(configs, 1):
        task_dir = output_dir / config_path.stem
        if args.resume and _task_done(task_dir):
            metadata = _read_json(task_dir / "metadata.json")
            metadata["status"] = "skipped"
            rows.append(metadata)
            print(f"[{idx}/{len(configs)}] skip {config_path.stem}")
            continue

        print(f"[{idx}/{len(configs)}] preview {config_path.stem}")
        row = run_one_config(
            config_path,
            config_dir=config_dir,
            output_dir=output_dir,
            debug_dir=debug_dir,
            repo_root=repo_root,
            geniesim_bin=args.geniesim_bin,
            num_instances=args.num_instances,
            instance_ids=instance_ids,
            dry_run=args.dry_run,
        )
        rows.append(row)
        write_index(output_dir, rows)
        if row.get("status") == "failed":
            failures += 1
            if args.fail_fast:
                break

    write_index(output_dir, rows)
    if failures:
        print(f"\nPreview gallery finished with {failures} failure(s).")
        return 1
    print(f"\nPreview gallery index: {output_dir / 'index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
