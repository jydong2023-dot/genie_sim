import ast
import json
from pathlib import Path

import pytest

from geniesim_benchmark.benchmark.scenario_config import (
    ScenarioConfig,
    apply_scenario_to_env,
    apply_scenario_to_task_config,
    load_scenario_config,
    scenario_cache_key,
    validate_vector_scenarios,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _write_scenario(task_dir: Path, instance_id: int, payload: dict) -> Path:
    instance_dir = task_dir / str(instance_id)
    instance_dir.mkdir(parents=True)
    path = instance_dir / "scenario.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_scenario_config_reads_runtime_overrides(tmp_path):
    task_dir = tmp_path / "arbitrary_task"
    _write_scenario(
        task_dir,
        12,
        {
            "instance_id": 12,
            "split": "standard",
            "dimension": "background",
            "background_usd": "background/room/room_2/background.usda",
            "light_config": {"temperature": 5000, "intensity": 1000},
            "parameters": {"table_height_offset": 0.0},
        },
    )

    scenario = load_scenario_config(task_dir, 12)

    assert scenario is not None
    assert scenario.instance_id == 12
    assert scenario.split == "standard"
    assert scenario.dimension == "background"
    assert scenario.background_usd == "background/room/room_2/background.usda"
    assert scenario.light_config == {"temperature": 5000, "intensity": 1000}


def test_load_scenario_config_returns_none_when_sidecar_is_missing(tmp_path):
    assert load_scenario_config(tmp_path, 99) is None


@pytest.mark.parametrize(
    "payload",
    [
        {
            "instance_id": 13,
            "split": "standard",
            "dimension": "background",
            "background_usd": None,
            "light_config": {},
        },
        {
            "instance_id": 12,
            "split": "standard",
            "dimension": "lighting",
            "background_usd": None,
            "light_config": [5000, 1000],
        },
    ],
)
def test_load_scenario_config_rejects_invalid_runtime_metadata(tmp_path, payload):
    task_dir = tmp_path / "arbitrary_task"
    path = _write_scenario(task_dir, 12, payload)

    with pytest.raises(ValueError, match=str(path)):
        load_scenario_config(task_dir, 12)


def _runtime_scenario(instance_id=12, background=None, light=None):
    return ScenarioConfig(
        instance_id=instance_id,
        split="standard",
        dimension="background",
        background_usd=background,
        light_config=light or {},
    )


def test_apply_scenario_runtime_overrides_is_backward_compatible():
    task_config = {"scene": {"scene_usd": "background/room/room_3/background.usda"}}
    original = json.loads(json.dumps(task_config))

    apply_scenario_to_task_config(task_config, None)
    assert task_config == original

    scenario = _runtime_scenario(
        background="background/room/room_2/background.usda",
        light={"temperature": 5000, "intensity": 1000},
    )
    apply_scenario_to_task_config(task_config, scenario)
    assert task_config["scene"]["scene_usd"] == scenario.background_usd

    class Env:
        def __init__(self):
            self.light_config = None

        def set_light_config(self, light_config):
            self.light_config = light_config

    env = Env()
    apply_scenario_to_env(env, scenario)
    assert env.light_config == scenario.light_config
    assert scenario_cache_key(None) is None
    assert scenario_cache_key(scenario) == 12


def test_validate_vector_scenarios_rejects_mixed_visual_overrides():
    room_2 = _runtime_scenario(12, "background/room/room_2/background.usda")
    room_3 = _runtime_scenario(13, "background/room/room_3/background.usda")
    validate_vector_scenarios([room_2, _runtime_scenario(14, room_2.background_usd)])

    with pytest.raises(ValueError, match="different backgrounds"):
        validate_vector_scenarios([room_2, room_3])

    warm = _runtime_scenario(
        18, room_2.background_usd, {"temperature": 3000, "intensity": 500}
    )
    cool = _runtime_scenario(
        19, room_2.background_usd, {"temperature": 9000, "intensity": 500}
    )
    with pytest.raises(ValueError, match="different light configurations"):
        validate_vector_scenarios([warm, cool])


def test_benchmark_runtime_wires_scenario_overrides_and_isolated_scene_cache():
    task_benchmark_path = (
        PACKAGE_ROOT
        / "src"
        / "geniesim_benchmark"
        / "benchmark"
        / "task_benchmark.py"
    )
    task_source = task_benchmark_path.read_text(encoding="utf-8")
    assert "load_scenario_config(" in task_source
    assert "apply_scenario_to_task_config(" in task_source
    assert "apply_scenario_to_env(" in task_source
    assert "validate_vector_scenarios(" in task_source
    assert "scene_variant_key=scenario_cache_key(" in task_source

    api_core_path = (
        PACKAGE_ROOT
        / "src"
        / "geniesim_benchmark"
        / "app"
        / "controllers"
        / "api_core.py"
    )
    api_tree = ast.parse(api_core_path.read_text(encoding="utf-8"), filename=str(api_core_path))
    functions = {
        node.name: node
        for node in ast.walk(api_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ("init_robot_cfg", "_init_robot_cfg"):
        assert "scene_variant_key" in [argument.arg for argument in functions[name].args.args]


def test_scene_variant_reload_preserves_robot_articulation():
    api_core_path = (
        PACKAGE_ROOT
        / "src"
        / "geniesim_benchmark"
        / "app"
        / "controllers"
        / "api_core.py"
    )
    api_source = api_core_path.read_text(encoding="utf-8")
    api_tree = ast.parse(api_source, filename=str(api_core_path))
    functions = {
        node.name: node
        for node in ast.walk(api_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "_replace_background_scene" in functions
    init_source = ast.get_source_segment(api_source, functions["_init_robot_cfg"])
    assert "self._loaded_scene_key[0] == robot_cfg" in init_source
    assert "self._replace_background_scene(scene_usd_path)" in init_source
