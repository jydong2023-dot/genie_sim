"""Formatting helpers for benchmark camera render profiling."""

from __future__ import annotations

from typing import Any


HEAD_CAMERA_NAMES = frozenset({"head_camera", "head_front_camera"})


def is_head_camera_name(camera_name: str) -> bool:
    return camera_name.lower() in HEAD_CAMERA_NAMES


def format_render_profile(
    *,
    camera_name: str,
    env_idx: int,
    render_wait_ms: float,
    get_data_ms: float,
    shape: Any,
    subframes: int,
) -> str:
    total_ms = render_wait_ms + get_data_ms
    return (
        f"[render_profile] env={env_idx} camera={camera_name} "
        f"render_wait_ms={render_wait_ms:.2f} get_data_ms={get_data_ms:.2f} "
        f"total_ms={total_ms:.2f} shape={shape} subframes={subframes}"
    )


def format_frame_profile(
    *,
    frame_idx: int,
    render_enabled: bool,
    world_step_ms: float,
    render_step_ms: float,
) -> str:
    total_ms = world_step_ms + render_step_ms
    return (
        f"[frame_profile] frame={frame_idx} render_enabled={render_enabled} "
        f"world_step_ms={world_step_ms:.2f} render_step_ms={render_step_ms:.2f} "
        f"total_ms={total_ms:.2f}"
    )
