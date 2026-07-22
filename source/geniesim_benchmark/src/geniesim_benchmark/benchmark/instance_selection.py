"""Scene-instance selection shared by benchmark runs and preview tooling."""

from __future__ import annotations

from collections.abc import Iterable


def select_scene_instance_ids(
    available_ids: Iterable[int], requested: str = ""
) -> list[int]:
    """Validate and select exact comma-separated scene instance IDs."""
    available = sorted(int(value) for value in available_ids)
    if not requested or not requested.strip():
        return available
    try:
        selected = [int(value.strip()) for value in requested.split(",") if value.strip()]
    except ValueError as exc:
        raise ValueError(
            f"benchmark.instance_ids must be comma-separated integers: {requested!r}"
        ) from exc
    if not selected:
        raise ValueError("benchmark.instance_ids must contain at least one integer")
    if len(selected) != len(set(selected)):
        raise ValueError(f"benchmark.instance_ids contains duplicate IDs: {selected}")
    missing = sorted(set(selected) - set(available))
    if missing:
        raise ValueError(
            f"requested scene instance IDs do not exist: {missing}; available: {available}"
        )
    return sorted(selected)

