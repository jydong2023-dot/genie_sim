# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Per-instance scenario overrides for benchmark task bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScenarioConfig:
    instance_id: int
    split: str
    dimension: str
    background_usd: str | None
    light_config: dict[str, int]


def _invalid(path: Path, message: str) -> ValueError:
    return ValueError(f"Invalid scenario config {path}: {message}")


def load_scenario_config(task_dir: Path, instance_id: int) -> ScenarioConfig | None:
    """Load runtime-owned overrides for one numeric task instance."""
    path = Path(task_dir) / str(instance_id) / "scenario.json"
    if not path.is_file():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _invalid(path, str(exc)) from exc

    if not isinstance(payload, dict):
        raise _invalid(path, "root must be an object")
    if payload.get("instance_id") != instance_id:
        raise _invalid(path, f"instance_id must be {instance_id}")

    split = payload.get("split")
    dimension = payload.get("dimension")
    background_usd = payload.get("background_usd")
    light_config = payload.get("light_config", {})

    if not isinstance(split, str) or not split:
        raise _invalid(path, "split must be a non-empty string")
    if not isinstance(dimension, str) or not dimension:
        raise _invalid(path, "dimension must be a non-empty string")
    if background_usd is not None and (not isinstance(background_usd, str) or not background_usd):
        raise _invalid(path, "background_usd must be null or a non-empty string")
    if not isinstance(light_config, dict):
        raise _invalid(path, "light_config must be an object")

    return ScenarioConfig(
        instance_id=instance_id,
        split=split,
        dimension=dimension,
        background_usd=background_usd,
        light_config=dict(light_config),
    )


def apply_scenario_to_task_config(task_config: dict, scenario: ScenarioConfig | None) -> None:
    """Apply the instance-owned background override in place."""
    if scenario is None or scenario.background_usd is None:
        return
    task_config["scene"]["scene_usd"] = scenario.background_usd


def apply_scenario_to_env(env, scenario: ScenarioConfig | None) -> None:
    """Store fixed light parameters for the existing generalization path."""
    if scenario is not None:
        env.set_light_config(dict(scenario.light_config))


def scenario_cache_key(scenario: ScenarioConfig | None) -> int | None:
    """Force scenario instances to use isolated background stage state."""
    return scenario.instance_id if scenario is not None else None


def validate_vector_scenarios(scenarios: list[ScenarioConfig | None]) -> None:
    """Reject visual overrides that cannot share one cloned vector stage."""
    configured = [scenario for scenario in scenarios if scenario is not None]
    backgrounds = {scenario.background_usd for scenario in configured}
    if len(backgrounds) > 1:
        details = ", ".join(f"{scenario.instance_id}:{scenario.background_usd}" for scenario in configured)
        raise ValueError(f"Vectorized instances use different backgrounds: {details}")

    lights = {json.dumps(scenario.light_config, sort_keys=True) for scenario in configured}
    if len(lights) > 1:
        details = ", ".join(f"{scenario.instance_id}:{scenario.light_config}" for scenario in configured)
        raise ValueError(f"Vectorized instances use different light configurations: {details}")
