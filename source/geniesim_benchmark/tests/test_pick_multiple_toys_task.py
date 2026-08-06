import json
from pathlib import Path

import pytest
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src" / "geniesim_benchmark"
ASSET_ROOT = Path("/home/user/djy/geniesim_assets")
CONFIG_PATH = SRC_ROOT / "config" / "g2op_if_pick_multiple_toys.yaml"
EVAL_PATH = SRC_ROOT / "benchmark" / "config" / "eval_tasks" / "pick_multiple_toys.json"
INSTANCE_DIR = SRC_ROOT / "benchmark" / "config" / "llm_task" / "pick_multiple_toys" / "0"
WRAPPER_PATH = ASSET_ROOT / "background" / "olalab" / "home_toy_scene_pick_toy.usda"

TARGETS = (
    ("blue_block", "right"),
    ("stacked_block_1", "left"),
    ("yellow_push_toy", "left"),
)
OBJECT_ROOT = "/World/toyscene/Objects"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pick_multiple_toys_config_contract():
    run_config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    eval_task = _load_json(EVAL_PATH)

    assert run_config["benchmark"] == {
        "task_name": "pick_multiple_toys",
        "platform": "g2_op",
        "sub_task_name": "pick_multiple_toys",
        "seed": 1,
        "model_arc": "corobot",
        "num_episode": 1,
        "num_instances": 1,
        "preview": False,
        "record": False,
    }
    assert eval_task["task_type"] == "pick_multiple_toys"
    assert eval_task["robot"]["arm"] == "dual"
    assert eval_task["robot"]["robot_cfg"] == "G2_omnipicker.json"
    assert eval_task["robot"]["robot_id"] == "G2"
    assert eval_task["recording_setting"]["num_of_episode"] == 3
    assert eval_task["scene"]["scene_usd"] == "/background/olalab/home_toy_scene_pick_toy.usda"
    assert eval_task["scene"]["scene_id"].endswith("/workspace_00")
    assert eval_task["stages"][0]["passive"]["object_id"] == ""


def test_pick_multiple_toys_has_three_ordered_pick_episodes():
    instructions_payload = _load_json(INSTANCE_DIR / "instructions.json")
    problems = _load_json(INSTANCE_DIR / "problems.json")
    scene_info = _load_json(INSTANCE_DIR / "scene_info.json")

    assert instructions_payload["instruction_category"] == "pick_multiple_toys"
    instructions = instructions_payload["instructions"]
    assert len(instructions) == 3
    assert len(problems) == 3
    assert list(scene_info["layout"]) == [target for target, _ in TARGETS]

    for index, (target, side) in enumerate(TARGETS, start=1):
        instruction = instructions[index - 1]
        problem = problems[f"problem{index}"]
        target_path = f"{OBJECT_ROOT}/{target}"

        assert instruction["id"] == index
        assert instruction["target"]["id1"] == target
        assert instruction["gripper"]["1"]["side"] == side
        assert problem["Problem"] == "pick_multiple_toys"
        action_list = problem["Acts"][0]["ActionList"]
        assert action_list[0]["ActionSetWaitAny"][0]["Follow"].startswith(
            target_path + "|"
        )
        assert action_list[1]["ActionSetWaitAny"][0]["PickUpOnGripper"] == (
            target_path + f"|{side}_gripper"
        )


def test_pick_multiple_toys_scene_metadata_matches_measured_targets():
    layout = _load_json(INSTANCE_DIR / "scene_info.json")["layout"]

    assert layout["blue_block"]["xyz"] == pytest.approx(
        [0.037945, -0.28145, 0.751435], abs=1e-6
    )
    assert layout["blue_block"]["description"]["dimensions"] == pytest.approx(
        [0.091028, 0.091995, 0.061508], abs=1e-6
    )
    assert layout["stacked_block_1"]["xyz"] == pytest.approx(
        [-0.22177, -0.082271, 0.751232], abs=1e-6
    )
    assert layout["stacked_block_1"]["description"]["dimensions"] == pytest.approx(
        [0.107421, 0.100965, 0.061723], abs=1e-6
    )
    assert layout["yellow_push_toy"]["xyz"] == pytest.approx(
        [-0.057001, 0.064307, 0.735737], abs=1e-6
    )
    assert layout["yellow_push_toy"]["description"]["dimensions"] == pytest.approx(
        [0.166134, 0.165766, 0.114624], abs=1e-6
    )


def test_wrapper_renames_toys_and_preserves_materials_and_physics():
    Usd = pytest.importorskip("pxr.Usd")
    UsdGeom = pytest.importorskip("pxr.UsdGeom")
    UsdPhysics = pytest.importorskip("pxr.UsdPhysics")
    UsdShade = pytest.importorskip("pxr.UsdShade")

    stage = Usd.Stage.Open(str(WRAPPER_PATH))
    assert stage is not None
    for old_name in ("yellow_plush_boy", "blue_plush_boy"):
        old_prim = stage.GetPrimAtPath(f"{OBJECT_ROOT}/{old_name}")
        assert old_prim.IsValid()
        assert not old_prim.IsActive()

    expected_materials = {
        "yellow_push_toy": "/World/toyscene/Materials/Material_01_01",
        "blue_push_toy": "/World/toyscene/Materials/Material_02_02",
    }
    for target, material_path in expected_materials.items():
        prim = stage.GetPrimAtPath(f"{OBJECT_ROOT}/{target}")
        assert prim.IsValid() and prim.IsActive()
        assert any(child.HasAPI(UsdPhysics.CollisionAPI) for child in Usd.PrimRange(prim))
        mesh = next(child for child in Usd.PrimRange(prim) if child.IsA(UsdGeom.Mesh))
        assert str(UsdShade.MaterialBindingAPI(mesh).ComputeBoundMaterial()[0].GetPath()) == material_path

    yellow = stage.GetPrimAtPath(f"{OBJECT_ROOT}/yellow_push_toy")
    assert yellow.HasAPI(UsdPhysics.RigidBodyAPI)
    assert UsdPhysics.RigidBodyAPI(yellow).GetRigidBodyEnabledAttr().Get() is True
    assert UsdPhysics.RigidBodyAPI(yellow).GetKinematicEnabledAttr().Get() is False
    assert UsdPhysics.MassAPI(yellow).GetMassAttr().Get() == pytest.approx(0.1)


def test_pick_multiple_toys_runtime_registrations():
    from geniesim_benchmark.benchmark.config.robot_init_states import (
        G2_DEFAULT_STATES,
        TASK_INFO_DICT,
    )
    from geniesim_benchmark.benchmark.config.task_config_mapping import TASK_MAPPING
    from geniesim_benchmark.plugins.output_system.eval_utils import TASK_STEPS

    assert TASK_INFO_DICT["pick_multiple_toys"]["G2_omnipicker"] is G2_DEFAULT_STATES
    assert TASK_STEPS["pick_multiple_toys"] == ["Follow", "PickUpOnGripper"]
    assert TASK_MAPPING["pick_multiple_toys"] == {
        "background": {"G2": "pick_multiple_toys"},
        "eval_dims": {"manip": "pick", "cognition": "semantic"},
    }
