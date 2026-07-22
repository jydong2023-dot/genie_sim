"""Standalone command line interface for scene-bundle augmentation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scenario_augmentation import (
    describe_scene,
    generate_augmented_scenarios,
    load_profile,
)


DEFAULT_SEED = 20260720


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-dir",
        type=Path,
        required=True,
        help="Explicit task directory containing numeric scene bundles.",
    )
    parser.add_argument("--source-instance", type=int, default=0)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--list-objects", action="store_true")
    parser.add_argument("--replace-generated", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    task_dir = args.task_dir.expanduser().resolve()
    if not task_dir.is_dir():
        raise FileNotFoundError(f"task directory does not exist: {task_dir}")
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
        f"Generated {len(specs)} scenarios in {task_dir}: "
        + ",".join(str(spec.instance_id) for spec in specs)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
