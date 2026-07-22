#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Generate deterministic augmented scenarios from any GenieSim LLM task."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
STANDALONE_SRC = SCRIPT_DIR.parents[1] / "scene_augmentation" / "src"
if STANDALONE_SRC.is_dir() and str(STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(STANDALONE_SRC))

from scene_augmentation import (  # noqa: E402
    describe_scene,
    generate_augmented_scenarios,
    load_profile,
)
from preview_task_gallery import (  # noqa: E402
    build_contact_sheet,
    default_config_dir,
    discover_repo_root,
    find_task_configs,
    run_one_config,
)


DEFAULT_SEED = 20260720


def llm_task_root() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "geniesim_benchmark"
        / "benchmark"
        / "config"
        / "llm_task"
    )


def resolve_task_dir(task: str | Path) -> Path:
    """Resolve either a task name under llm_task or an explicit task path."""
    candidate = Path(task).expanduser()
    if candidate.is_dir():
        return candidate.resolve()
    named = llm_task_root() / candidate
    if named.is_dir():
        return named.resolve()
    raise FileNotFoundError(
        f"task does not exist as a path or llm_task name: {task}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task",
        required=True,
        help="Task name under llm_task, or an explicit task directory.",
    )
    parser.add_argument(
        "--source-instance",
        type=int,
        default=0,
        help="Numeric source instance inside --task (default: 0).",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        help="Augmentation profile JSON; defaults cover pose/light/table variants.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=40,
        help="Number of scenarios to generate (default: 40).",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--list-objects",
        action="store_true",
        help="Print auto-discovered movable/table IDs and exit without writing.",
    )
    parser.add_argument(
        "--replace-generated",
        action="store_true",
        help="Replace existing numeric scenarios while preserving non-generated files.",
    )
    parser.add_argument(
        "--skip-preview",
        action="store_true",
        help="Generate scenes without launching the default benchmark previews.",
    )
    parser.add_argument(
        "--preview-config",
        type=Path,
        help="Benchmark YAML to use for preview (auto-detected by sub_task_name by default).",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=default_config_dir(),
        help="Benchmark YAML directory used for automatic preview config discovery.",
    )
    parser.add_argument(
        "--preview-output-dir",
        type=Path,
        help="Preview root (default: <task>/previews/generated_<first>_<last>).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="GenieSim checkout root used by benchmark preview.",
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        help="Simulator debug_preview directory override.",
    )
    parser.add_argument(
        "--geniesim-bin",
        default="geniesim",
        help="geniesim executable used for preview (default: geniesim).",
    )
    return parser.parse_args(argv)


def _resolve_preview_config(args: argparse.Namespace, task_dir: Path) -> Path:
    if args.preview_config:
        config = args.preview_config.expanduser().resolve()
        if not config.is_file():
            raise FileNotFoundError(f"preview config does not exist: {config}")
        return config
    config_dir = args.config_dir.expanduser().resolve()
    matches = find_task_configs(config_dir, task_dir.name)
    if not matches:
        raise FileNotFoundError(
            f"no benchmark YAML has sub_task_name={task_dir.name!r} under {config_dir}; "
            "pass --preview-config or --skip-preview"
        )
    if len(matches) > 1:
        print(
            f"Multiple preview configs match {task_dir.name}; using {matches[0].name}",
            file=sys.stderr,
        )
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    task_dir = resolve_task_dir(args.task)
    source_dir = task_dir / str(args.source_instance)
    profile = load_profile(args.profile)
    if args.list_objects:
        print(json.dumps(describe_scene(source_dir, profile), indent=2, sort_keys=True))
        return 0

    specs = generate_augmented_scenarios(
        source_dir,
        task_dir,
        count=args.count,
        seed=args.seed,
        profile=profile,
        replace_generated=args.replace_generated,
    )
    print(
        f"Generated {len(specs)} augmented scenarios from {source_dir} in {task_dir}"
    )
    generated_ids = [spec.instance_id for spec in specs]
    if not args.skip_preview:
        config = _resolve_preview_config(args, task_dir)
        repo_root = (
            args.repo_root.expanduser().resolve()
            if args.repo_root
            else discover_repo_root(start=task_dir)
        )
        debug_dir = (
            args.debug_dir.expanduser().resolve()
            if args.debug_dir
            else repo_root / "debug_preview"
        )
        run_name = f"generated_{generated_ids[0]}_{generated_ids[-1]}"
        preview_root = (
            args.preview_output_dir.expanduser().resolve()
            if args.preview_output_dir
            else task_dir / "previews" / run_name
        )
        metadata = run_one_config(
            config,
            config_dir=config.parent,
            output_dir=preview_root,
            debug_dir=debug_dir,
            repo_root=repo_root,
            geniesim_bin=args.geniesim_bin,
            num_instances=0,
            instance_ids=generated_ids,
        )
        if metadata["status"] != "ok":
            raise RuntimeError(
                f"preview failed after scene generation; see {metadata['task_dir']}/metadata.json"
            )
        contact_sheet = build_contact_sheet(
            Path(metadata["task_dir"]), generated_ids
        )
        print(f"Saved previews in {metadata['task_dir']}")
        print(f"Saved contact sheet: {contact_sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
