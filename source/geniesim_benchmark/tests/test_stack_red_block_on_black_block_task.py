import ast
import json
import math
from pathlib import Path

import numpy as np
import pytest
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "geniesim_benchmark"
TASK_NAME = "stack_red_block_on_black_block"
RED_ID = "red_block_000"
BLACK_ID = "black_block_000"
CONFIG_PATH = PACKAGE_ROOT / "config" / "g2op_spatial_stack_red_block_on_black_block.yaml"
TASK_ROOT = PACKAGE_ROOT / "benchmark" / "config" / "llm_task" / TASK_NAME
TASK_DIR = TASK_ROOT / "0"


def _assigned_dict(path: Path, assignment_name: str) -> ast.Dict:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == assignment_name for target in node.targets):
            assert isinstance(node.value, ast.Dict)
            return node.value
    raise AssertionError(f"{assignment_name} not found in {path}")


def _dict_entry(path: Path, assignment_name: str, entry_name: str) -> ast.AST:
    dictionary = _assigned_dict(path, assignment_name)
    for key, value in zip(dictionary.keys, dictionary.values):
        if key is not None and ast.literal_eval(key) == entry_name:
            return value
    raise AssertionError(f"{entry_name} not found in {assignment_name} at {path}")


def _evaluate_ontop(red_aabb, black_aabb):
    ontop_path = PACKAGE_ROOT / "plugins" / "ader" / "action" / "custom" / "ontop.py"
    tree = ast.parse(ontop_path.read_text(encoding="utf-8"), filename=str(ontop_path))
    ontop_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Ontop"
    )

    class EvaluateAction:
        def update(self, delta_time):
            return delta_time

    namespace = {
        "EvaluateAction": EvaluateAction,
        "ActionBase": object,
        "ActionEvent": object,
        "logger": None,
        "np": np,
    }
    exec(compile(ast.Module(body=[ontop_class], type_ignores=[]), str(ontop_path), "exec"), namespace)

    action = namespace["Ontop"].__new__(namespace["Ontop"])
    action.active_obj = RED_ID
    action.passive_obj = BLACK_ID
    action._done_flag = False
    action.threshold = 0.5
    aabbs = {RED_ID: red_aabb, BLACK_ID: black_aabb}
    action.get_obj_aabb_new = lambda object_id: tuple(np.array(v) for v in aabbs[object_id])
    action.update(0.0)
    return action._is_done()


def test_entry_config_selects_g2_table_task_and_new_subtask():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["benchmark"] == {
        "task_name": "table_task_2_g2_op",
        "platform": "g2_op",
        "sub_task_name": TASK_NAME,
        "seed": 1,
        "model_arc": "corobot",
        "num_episode": 1,
        "num_instances": 0,
        "record": False,
    }


def test_repository_contains_complete_40_scenario_suite():
    numeric_ids = sorted(int(path.name) for path in TASK_ROOT.iterdir() if path.is_dir() and path.name.isdigit())
    assert numeric_ids == list(range(40))

    required_files = {
        "scene.usda",
        "scene_info.json",
        "instructions.json",
        "problems.json",
        "scenario.json",
    }
    manifest = json.loads((TASK_ROOT / "scenario_manifest.json").read_text(encoding="utf-8"))
    assert manifest["scenario_count"] == 40
    assert [entry["instance_id"] for entry in manifest["scenarios"]] == list(range(40))

    for entry in manifest["scenarios"]:
        instance_dir = TASK_ROOT / str(entry["instance_id"])
        assert {path.name for path in instance_dir.iterdir()} == required_files
        assert json.loads((instance_dir / "scenario.json").read_text(encoding="utf-8")) == entry

        scene = (instance_dir / "scene.usda").read_text(encoding="utf-8")
        assert 'def Xform "red_block_000"' in scene
        assert 'def Xform "black_block_000"' in scene
        assert 'def Material "BlackMaterial"' in scene

        instructions = json.loads((instance_dir / "instructions.json").read_text(encoding="utf-8"))
        assert instructions["task_id"] == f"{TASK_NAME}_{entry['instance_id']}"
        assert instructions["instructions"] == [
            {"instruction": "place the red block on top of the black block"}
        ]

        problems = json.loads((instance_dir / "problems.json").read_text(encoding="utf-8"))
        assert problems["problem1"]["Acts"][0]["ActionList"][0]["ActionSetWaitAny"][0] == {
            "Ontop": f"{RED_ID}|{BLACK_ID}"
        }


def test_scene_reuses_two_equal_cubes_and_binds_black_material():
    scene = (TASK_DIR / "scene.usda").read_text(encoding="utf-8")
    cube_payload = (
        "/geniesim_assets/objects/benchmark/building_blocks/"
        "benchmark_building_blocks_074/Aligned.usda"
    )

    assert scene.count(cube_payload) == 2
    assert 'def Xform "red_block_000"' in scene
    assert 'def Xform "black_block_000"' in scene
    assert 'def Material "BlackMaterial"' in scene
    assert 'uniform token info:id = "UsdPreviewSurface"' in scene
    assert "color3f inputs:diffuseColor = (0.01, 0.01, 0.01)" in scene
    assert 'rel material:binding = </World/Objects/black_block_000/Looks/BlackMaterial>' in scene


def test_scene_metadata_matches_visual_roles_and_safe_initial_placement():
    metadata = json.loads((TASK_DIR / "scene_info.json").read_text(encoding="utf-8"))
    layout = metadata["layout"]

    assert set(layout) == {RED_ID, BLACK_ID, "table_614a6115"}
    assert layout[RED_ID]["description"]["color"] == "red"
    assert layout[BLACK_ID]["description"]["color"] == "black"
    assert layout[RED_ID]["usd"] == "benchmark_building_blocks_074"
    assert layout[BLACK_ID]["usd"] == "benchmark_building_blocks_074"
    assert layout[RED_ID]["description"]["dimensions"] == [0.05, 0.05, 0.05]
    assert layout[BLACK_ID]["description"]["dimensions"] == [0.05, 0.05, 0.05]
    assert layout[RED_ID]["xyz"][2] == pytest.approx(0.885)
    assert layout[BLACK_ID]["xyz"][2] == pytest.approx(0.885)
    assert math.dist(layout[RED_ID]["xyz"][:2], layout[BLACK_ID]["xyz"][:2]) >= 0.12

    graph = metadata["relations"]["graph"]
    node_ids = {node["id"] for node in graph["nodes"]}
    assert set(layout).issubset(node_ids)
    assert all(link["source"] in node_ids and link["target"] in node_ids for link in graph["links"])


def test_instruction_is_explicit_about_red_on_black_order():
    instructions = json.loads((TASK_DIR / "instructions.json").read_text(encoding="utf-8"))

    assert instructions == {
        "instructions": [{"instruction": "place the red block on top of the black block"}],
        "task_id": "stack_red_block_on_black_block_0",
    }


def test_problem_uses_ordered_ontop_with_fall_and_timeout_guards():
    problems = json.loads((TASK_DIR / "problems.json").read_text(encoding="utf-8"))
    problem = problems["problem1"]
    wait_any = problem["Acts"][0]["ActionList"][0]["ActionSetWaitAny"]

    assert wait_any == [
        {"Ontop": f"{RED_ID}|{BLACK_ID}"},
        {"Onfloor": f"{RED_ID}|0"},
        {"Onfloor": f"{BLACK_ID}|0"},
        {"StepOut": 1500},
    ]
    assert problem["Problem"] == TASK_NAME
    assert all("Stack" not in leaf for leaf in wait_any)


def test_task_is_registered_for_g2_scoring_and_catalog_metadata():
    robot_entry = _dict_entry(
        PACKAGE_ROOT / "benchmark" / "config" / "robot_init_states.py",
        "TASK_INFO_DICT",
        TASK_NAME,
    )
    assert isinstance(robot_entry, ast.Dict)
    robot_mapping = {ast.literal_eval(key): value for key, value in zip(robot_entry.keys, robot_entry.values)}
    assert set(robot_mapping) == {"G2_omnipicker"}
    assert isinstance(robot_mapping["G2_omnipicker"], ast.Name)
    assert robot_mapping["G2_omnipicker"].id == "G2_DEFAULT_STATES"

    score_entry = _dict_entry(
        PACKAGE_ROOT / "plugins" / "output_system" / "eval_utils.py",
        "TASK_STEPS",
        TASK_NAME,
    )
    assert ast.literal_eval(score_entry) == ["Ontop"]

    catalog_entry = _dict_entry(
        PACKAGE_ROOT / "benchmark" / "config" / "task_config_mapping.py",
        "TASK_MAPPING",
        TASK_NAME,
    )
    assert ast.literal_eval(catalog_entry) == {
        "background": {"G2": "table_task_2_g2_op"},
        "eval_dims": {"manip": "spatial_pick_place", "cognition": "semantic"},
    }


@pytest.mark.parametrize(
    ("red_aabb", "black_aabb", "expected"),
    [
        (([0.10, 0.00, 0.05], [0.15, 0.05, 0.10]), ([0.00, 0.00, 0.00], [0.05, 0.05, 0.05]), False),
        (([0.00, 0.00, 0.00], [0.05, 0.05, 0.05]), ([0.00, 0.00, 0.05], [0.05, 0.05, 0.10]), False),
        (([0.03, 0.00, 0.05], [0.08, 0.05, 0.10]), ([0.00, 0.00, 0.00], [0.05, 0.05, 0.05]), False),
        (([0.02, 0.00, 0.05], [0.07, 0.05, 0.10]), ([0.00, 0.00, 0.00], [0.05, 0.05, 0.05]), True),
    ],
    ids=["beside", "black-on-red", "overlap-below-threshold", "red-on-black"],
)
def test_existing_ontop_checker_enforces_order_and_overlap(red_aabb, black_aabb, expected):
    assert _evaluate_ontop(red_aabb, black_aabb) is expected
