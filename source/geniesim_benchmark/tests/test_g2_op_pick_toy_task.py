import json
from pathlib import Path

import pytest
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src" / "geniesim_benchmark"
ASSET_ROOT = Path("/home/user/djy/geniesim_assets")
CONFIG_PATH = SRC_ROOT / "config" / "g2op_if_g2_op_pick_toy.yaml"
EVAL_PATH = SRC_ROOT / "benchmark" / "config" / "eval_tasks" / "g2_op_pick_toy.json"
INSTANCE_DIR = SRC_ROOT / "benchmark" / "config" / "llm_task" / "g2_op_pick_toy" / "0"
WRAPPER_PATH = ASSET_ROOT / "background" / "olalab" / "home_toy_scene_pick_toy.usda"
MATERIAL_OVERRIDES_PATH = ASSET_ROOT / "background" / "olalab" / "home_toy_scene_material_paths.usda"
TARGET_PATH = "/World/toyscene/Objects/blue_block"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_g2_op_pick_toy_config_contract():
    run_config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    eval_task = _load_json(EVAL_PATH)

    assert run_config["benchmark"] == {
        "task_name": "g2_op_pick_toy",
        "platform": "g2_op",
        "sub_task_name": "g2_op_pick_toy",
        "seed": 1,
        "model_arc": "corobot",
        "num_episode": 1,
        "num_instances": 1,
        "preview": False,
        "record": False,
    }
    assert eval_task["robot"]["robot_cfg"] == "G2_omnipicker.json"
    assert eval_task["robot"]["robot_id"] == "G2"
    assert eval_task["robot"]["robot_init_pose"]["workspace_00"] == {
        "position": [-0.71, 0.0, 0.0],
        "quaternion": [1.0, 0.0, 0.0, 0.0],
    }
    assert eval_task["scene"]["scene_usd"] == "/background/olalab/home_toy_scene_pick_toy.usda"
    assert eval_task["scene"]["scene_id"].endswith("/workspace_00")
    assert eval_task["stages"][0]["passive"]["object_id"] == TARGET_PATH


def test_g2_op_pick_toy_instance_contract():
    instructions = _load_json(INSTANCE_DIR / "instructions.json")
    problems = _load_json(INSTANCE_DIR / "problems.json")
    scene_info = _load_json(INSTANCE_DIR / "scene_info.json")
    scene_text = (INSTANCE_DIR / "scene.usda").read_text(encoding="utf-8")

    assert len(instructions["instructions"]) == 1
    instruction = instructions["instructions"][0]
    assert instruction["instruction"] == "Use the right arm to pick up the blue block on the table"
    assert instruction["target"]["idn"] == "blue_block"
    assert instruction["gripper"]["1"]["side"] == "right"

    action_list = problems["problem1"]["Acts"][0]["ActionList"]
    assert action_list[0]["ActionSetWaitAny"][0]["Follow"].startswith(TARGET_PATH + "|")
    assert action_list[1]["ActionSetWaitAny"][0]["PickUpOnGripper"] == TARGET_PATH + "|right_gripper"
    assert problems["problem1"]["Problem"] == "g2_op_pick_toy"

    target = scene_info["layout"]["blue_block"]
    assert target["description"]["semantic_name"] == ["block"]
    assert target["description"]["dimensions"] == pytest.approx(
        [0.091028, 0.091995, 0.061508], abs=1e-6
    )
    assert target["xyz"] == pytest.approx([0.037945, -0.28145, 0.751435], abs=1e-6)
    assert target["xyzw"] == pytest.approx([0.0, 0.0, -0.67559, 0.737277], abs=1e-6)
    assert 'def Xform "World"' in scene_text


def test_g2_op_pick_toy_wrapper_exposes_pickable_target():
    Usd = pytest.importorskip("pxr.Usd")
    UsdPhysics = pytest.importorskip("pxr.UsdPhysics")

    stage = Usd.Stage.Open(str(WRAPPER_PATH))
    assert stage is not None
    target = stage.GetPrimAtPath(TARGET_PATH)
    assert target.IsValid()
    assert target.HasAPI(UsdPhysics.RigidBodyAPI)
    assert UsdPhysics.RigidBodyAPI(target).GetRigidBodyEnabledAttr().Get() is True
    assert UsdPhysics.RigidBodyAPI(target).GetKinematicEnabledAttr().Get() is False
    assert any(prim.HasAPI(UsdPhysics.CollisionAPI) for prim in Usd.PrimRange(target))


def test_g2_op_pick_toy_scene_uses_portable_material_paths():
    override_text = MATERIAL_OVERRIDES_PATH.read_text(encoding="utf-8")
    assert "/home/user/djy/geniesim_assets/" not in override_text
    assert "../common/HDR/rostock_laage_airport_8k.hdr" in override_text

    Usd = pytest.importorskip("pxr.Usd")
    stage = Usd.Stage.Open(str(WRAPPER_PATH))
    dome_texture = stage.GetAttributeAtPath(
        "/World/light/Light_00/DomeLight/DomeLight.inputs:texture:file"
    ).Get()
    assert dome_texture.path == "../common/HDR/rostock_laage_airport_8k.hdr"
    toy_texture = stage.GetAttributeAtPath(
        "/World/toyscene/Materials/Material_00_00/BaseColorTexture.inputs:file"
    ).Get()
    assert toy_texture.path == "toy_scene/toyscene_textures/image_00.png"
    assert Path(toy_texture.resolvedPath).is_file()


def test_g2_op_pick_toy_runtime_registrations():
    from geniesim_benchmark.benchmark.config.robot_init_states import G2_DEFAULT_STATES, TASK_INFO_DICT
    from geniesim_benchmark.benchmark.config.task_config_mapping import TASK_MAPPING
    from geniesim_benchmark.plugins.output_system.eval_utils import TASK_STEPS

    assert TASK_INFO_DICT["g2_op_pick_toy"]["G2_omnipicker"] is G2_DEFAULT_STATES
    assert TASK_STEPS["g2_op_pick_toy"] == ["Follow", "PickUpOnGripper"]
    assert TASK_MAPPING["g2_op_pick_toy"] == {
        "background": {"G2": "g2_op_pick_toy"},
        "eval_dims": {"manip": "pick", "cognition": "semantic"},
    }
