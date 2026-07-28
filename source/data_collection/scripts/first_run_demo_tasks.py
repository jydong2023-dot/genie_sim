# -*- coding: utf-8 -*-
"""Task list and helper utilities for run_first_run_demos.py (no grpc/Isaac imports)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Same ordering as README_DEMO.md (easy → hard).
FIRST_RUN_DEMOS: list[dict[str, str]] = [
    {
        "index": "1",
        "label": "pick_red_billiard",
        "template": "tasks/geniesim_2025/pick_billards_of_specific_color/g2/pick_billards_of_specific_color_red.json",
    },
    {
        "index": "2",
        "label": "pick_red_block",
        "template": "tasks/geniesim_2025/pick_building_block_of_specific_color/g2/pick_building_block_of_specific_color_red.json",
    },
    {
        "index": "3",
        "label": "pick_stationery",
        "template": "tasks/geniesim_2025/pick_up_the_stationery/g2/pick_up_the_stationery.json",
    },
    {
        "index": "4",
        "label": "pick_smallest_apple",
        "template": "tasks/geniesim_2025/pick_fruit_of_specific_size/g2/pick_fruit_of_specific_size_apple_small_g2.json",
    },
    {
        "index": "5",
        "label": "place_block_into_box",
        "template": "tasks/geniesim_2025/place_blocks_into_box/g2/place_blocks_into_box_001.json",
    },
    {
        "index": "6",
        "label": "pen_into_holder",
        "template": "tasks/geniesim_2025/put_the_pen_into_the_pen_holder/g2/put_the_pen_into_the_pen_holder_g2.json",
    },
    {
        "index": "7",
        "label": "sort_apple",
        "template": "tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json",
    },
    {
        "index": "8",
        "label": "place_into_red_box",
        "template": "tasks/geniesim_2025/place_object_into_box_of_specific_color/g2/place_object_into_box_of_specific_color_red_g2.json",
    },
    {
        "index": "9",
        "label": "pick_non_red",
        "template": "tasks/geniesim_2025/pick_up_with_not_command/g2/pick_up_with_not_command_red.json",
    },
]


def parse_index_selection(raw: str | None, total: int) -> set[int]:
    if not raw:
        return set(range(1, total + 1))
    selected: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            selected.update(range(start, end + 1))
        else:
            selected.add(int(part))
    invalid = [i for i in selected if i < 1 or i > total]
    if invalid:
        raise ValueError(f"Task index out of range 1..{total}: {invalid}")
    return selected


def recording_root(root: Path) -> Path:
    return root / "recording_data"


def snapshot_recording_dirs(root: Path) -> set[str]:
    rec = recording_root(root)
    if not rec.is_dir():
        return set()
    return {p.name for p in rec.iterdir() if p.is_dir()}


def find_new_recording_dir(root: Path, before: set[str]) -> Path | None:
    rec = recording_root(root)
    if not rec.is_dir():
        return None
    candidates = [p for p in rec.iterdir() if p.is_dir() and p.name not in before]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def read_task_result(recording_dir: Path) -> dict[str, Any] | None:
    result_path = recording_dir / "task_result.json"
    if not result_path.is_file():
        return None
    with open(result_path, "r", encoding="utf-8") as f:
        return json.load(f)


def episode_success(recording_dir: Path) -> tuple[bool, dict[str, Any] | None]:
    result = read_task_result(recording_dir)
    if result is None:
        return False, None
    return bool(result.get("task_status")), result
