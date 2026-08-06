import json
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src" / "geniesim_benchmark"
ASSET_ROOT = Path("/home/user/djy/geniesim_assets")

sys.path.insert(0, str(PACKAGE_ROOT / "src"))

geniesim_assets = types.ModuleType("geniesim_assets")
geniesim_assets.ASSETS_PATH = str(ASSET_ROOT)
sys.modules.setdefault("geniesim_assets", geniesim_assets)


def _stub_api_core(monkeypatch):
    api_core_module = types.ModuleType("geniesim_benchmark.app.controllers.api_core")
    api_core_module.APICore = object
    monkeypatch.setitem(sys.modules, "geniesim_benchmark.app.controllers.api_core", api_core_module)


def test_dual_agx_nero_benchmark_configs_are_wired():
    robot_cfg_path = SRC_ROOT / "app" / "robot_cfg" / "dual_agx_nero.json"
    eval_task_path = SRC_ROOT / "benchmark" / "config" / "eval_tasks" / "table_task_dual_agx_nero.json"
    run_cfg_path = SRC_ROOT / "config" / "dual_agx_nero_if_pick_block_color.yaml"

    robot_cfg = json.loads(robot_cfg_path.read_text(encoding="utf-8"))
    eval_task = json.loads(eval_task_path.read_text(encoding="utf-8"))
    run_cfg = yaml.safe_load(run_cfg_path.read_text(encoding="utf-8"))

    assert robot_cfg["robot"]["robot_name"] == "dual_agx_nero"
    assert robot_cfg["robot"]["robot_generation"] == "dual_agx_nero"
    assert robot_cfg["robot"]["robot_usd"] == "robot/DualAgxNero/dual_agx_nero.usd"
    assert robot_cfg["camera"]["/dual_agx_nero/head_front_Camera"] == [640, 400, 30]
    assert robot_cfg["camera"]["/dual_agx_nero/left_gripper_base/Left_Camera"] == [640, 400, 30]
    assert robot_cfg["camera"]["/dual_agx_nero/right_gripper_base/Right_Camera"] == [640, 400, 30]

    robot_usd_path = ASSET_ROOT / robot_cfg["robot"]["robot_usd"]
    assert robot_usd_path.exists()

    assert eval_task["robot"]["robot_cfg"] == "dual_agx_nero.json"
    assert eval_task["robot"]["robot_id"] == "dual_agx_nero"
    assert eval_task["task"] == "table_task_1_g2_op"
    assert eval_task["recording_setting"]["camera_list"] == [
        "/dual_agx_nero/head_front_Camera",
        "/dual_agx_nero/left_gripper_base/Left_Camera",
        "/dual_agx_nero/right_gripper_base/Right_Camera",
    ]

    assert run_cfg["benchmark"]["task_name"] == "table_task_dual_agx_nero"
    assert run_cfg["benchmark"]["platform"] == "dual_agx_nero"
    assert run_cfg["benchmark"]["sub_task_name"] == "pick_block_color"
    assert run_cfg["benchmark"]["policy_class"] == "DemoPolicy"
    assert run_cfg["benchmark"]["env_class"] == "DummyEnv"


def test_dual_agx_nero_fake_joint_abs_smoke_config_is_wired():
    run_cfg_path = SRC_ROOT / "config" / "dual_agx_nero_fake_joint_abs_pick_block_color.yaml"
    run_cfg = yaml.safe_load(run_cfg_path.read_text(encoding="utf-8"))

    assert run_cfg["benchmark"]["task_name"] == "table_task_dual_agx_nero"
    assert run_cfg["benchmark"]["platform"] == "dual_agx_nero"
    assert run_cfg["benchmark"]["sub_task_name"] == "pick_block_color"
    assert run_cfg["benchmark"]["model_arc"] == "fake_joint_abs"
    assert run_cfg["benchmark"]["policy_class"] == "FakeJointAbsPolicy"
    assert run_cfg["benchmark"]["env_class"] == "PiEnv"


def test_dual_agx_nero_scripted_joint_abs_smoke_config_is_wired():
    run_cfg_path = SRC_ROOT / "config" / "dual_agx_nero_scripted_joint_abs_pick_block_color.yaml"
    run_cfg = yaml.safe_load(run_cfg_path.read_text(encoding="utf-8"))

    assert run_cfg["benchmark"]["task_name"] == "table_task_dual_agx_nero"
    assert run_cfg["benchmark"]["platform"] == "dual_agx_nero"
    assert run_cfg["benchmark"]["sub_task_name"] == "pick_block_color"
    assert run_cfg["benchmark"]["model_arc"] == "scripted_joint_abs"
    assert run_cfg["benchmark"]["policy_class"] == "ScriptedJointAbsPolicy"
    assert run_cfg["benchmark"]["env_class"] == "PiEnv"
    assert run_cfg["benchmark"]["scripted_policy_save_observation_images"] is True


def test_debug_cli_params_are_available(monkeypatch):
    from geniesim_benchmark.config.params import (
        AppConfig,
        BenchmarkConfig,
        Config,
        ParameterServer,
        declare_dataclass_params,
        load_dataclass,
    )

    assert BenchmarkConfig().keep_open is False
    assert AppConfig().enable_physics_inspector is False
    assert AppConfig().show_physics_inspector is False

    monkeypatch.setenv("SIM_REPO_ROOT", str(PACKAGE_ROOT))

    ps = ParameterServer()
    declare_dataclass_params(Config, ps)
    ps.override_from_cli(
        [
            "--benchmark.keep_open=true",
            "--app.enable_physics_inspector=true",
            "--app.show_physics_inspector=true",
        ]
    )
    cfg = load_dataclass(Config, ps)

    assert cfg.benchmark.keep_open is True
    assert cfg.app.enable_physics_inspector is True
    assert cfg.app.show_physics_inspector is True


def test_dual_agx_nero_runtime_mappings_are_available():
    from geniesim_benchmark.benchmark.config.robot_init_states import TASK_INFO_DICT
    from geniesim_benchmark.utils.infer_pre_process import TaskInfo
    from geniesim_benchmark.utils.name_utils import ROBOT_CONFIGS, robot_type_mapping

    assert robot_type_mapping("dual_agx_nero") == "dual_agx_nero"

    cfg = ROBOT_CONFIGS["dual_agx_nero"]
    assert cfg["left_arm_joints"] == [f"left_joint{i}" for i in range(1, 8)]
    assert cfg["right_arm_joints"] == [f"right_joint{i}" for i in range(1, 8)]
    assert cfg["arm_joints"] == cfg["left_arm_joints"] + cfg["right_arm_joints"]
    assert cfg["gripper_joints"] == ["left_gripper", "right_gripper"]
    assert cfg["init_gripper_open"] == [0.1, 0.1]

    task_info_cfg = TASK_INFO_DICT["pick_block_color"]["dual_agx_nero"]
    init_arm, init_head, init_waist, _init_hand, init_gripper = TaskInfo(
        task_info_cfg, "dual_agx_nero"
    ).init_pose()

    assert len(init_arm) == 14
    assert init_arm[:7] == [2.6, -1.2, 0.0, -0.4, 0.0, 0.4, 0.0]
    assert init_arm[7:] == [0.5, -1.2, 0.0, -0.4, 0.0, 0.4, 0.0]
    assert init_head == []
    assert init_waist == []
    assert init_gripper == [0.1, 0.1]


def test_dual_agx_nero_camera_dirs_are_available(monkeypatch):
    _stub_api_core(monkeypatch)

    from geniesim_benchmark.utils.data_courier import DataCourier

    data_courier = DataCourier.__new__(DataCourier)
    data_courier.robot_cfg = "dual_agx_nero"

    assert data_courier._camera_dirs() == {
        "head": "head_front_camera",
        "left_hand": "left_camera",
        "right_hand": "right_camera",
    }


def test_fake_joint_abs_policy_generates_dual_agx_actions(monkeypatch):
    _stub_api_core(monkeypatch)

    from geniesim_benchmark.benchmark.config.robot_init_states import DUAL_AGX_NERO_DEFAULT_STATES
    from geniesim_benchmark.benchmark.policy.fake_joint_abs_policy import FakeJointAbsPolicy

    init_arm = DUAL_AGX_NERO_DEFAULT_STATES["init_arm"]
    observation = {
        "states": {
            "left_arm": init_arm[:7],
            "right_arm": init_arm[7:],
            "left_gripper": [0.1],
            "right_gripper": [0.1],
            "waist": [],
            "head": [],
        }
    }

    policy = FakeJointAbsPolicy(robot_cfg="dual_agx_nero", max_steps=2, amplitude=0.04)

    first_action = policy.act(observation)
    second_action = policy.act(observation)
    terminal_action = policy.act(observation)

    assert first_action["kind"] == "JOINT_ABS"
    assert len(first_action["arm"]) == 14
    assert len(first_action["gripper"]) == 2
    assert first_action["gripper"] == [0.1, 0.1]
    assert first_action["arm"] != init_arm
    assert second_action["arm"] != first_action["arm"]
    assert terminal_action is None


def test_scripted_joint_abs_policy_uses_dual_agx_home_pose(tmp_path, monkeypatch):
    _stub_api_core(monkeypatch)

    from geniesim_benchmark.benchmark.config.robot_init_states import DUAL_AGX_NERO_DEFAULT_STATES
    from geniesim_benchmark.benchmark.policy.scripted_joint_abs_policy import ScriptedJointAbsPolicy

    init_arm = DUAL_AGX_NERO_DEFAULT_STATES["init_arm"]
    observation = {
        "images": {},
        "states": {
            "left_arm": init_arm[:7],
            "right_arm": init_arm[7:],
            "left_gripper": [0.1],
            "right_gripper": [0.1],
            "waist": [],
            "head": [],
        },
    }
    monkeypatch.setenv("SIM_REPO_ROOT", str(tmp_path))

    policy = ScriptedJointAbsPolicy(
        task_name="table_task_dual_agx_nero",
        sub_task_name="pick_block_color",
        robot_cfg="dual_agx_nero",
        save_observation_images=False,
    )

    first_action = policy.act(observation)
    for _ in range(120):
        action = policy.act(observation)
    close_or_lift_action = action

    assert first_action["kind"] == "JOINT_ABS"
    assert first_action["arm"] == init_arm
    assert first_action["gripper"] == [0.1, 0.1]

    assert close_or_lift_action["kind"] == "JOINT_ABS"
    assert close_or_lift_action["arm"][:7] != close_or_lift_action["arm"][7:]
    assert close_or_lift_action["arm"][1:7] == close_or_lift_action["arm"][8:14]
    assert close_or_lift_action["gripper"] == [0.0, 0.0]

    for _ in range(policy.total_steps):
        terminal_action = policy.act(observation)
    assert terminal_action is None


def test_scripted_joint_abs_policy_closes_and_reopens_gripper(tmp_path, monkeypatch):
    _stub_api_core(monkeypatch)

    from geniesim_benchmark.benchmark.config.robot_init_states import DUAL_AGX_NERO_DEFAULT_STATES
    from geniesim_benchmark.benchmark.policy.scripted_joint_abs_policy import ScriptedJointAbsPolicy

    init_arm = DUAL_AGX_NERO_DEFAULT_STATES["init_arm"]
    observation = {
        "images": {},
        "states": {
            "left_arm": init_arm[:7],
            "right_arm": init_arm[7:],
            "left_gripper": [0.1],
            "right_gripper": [0.1],
            "waist": [],
            "head": [],
        },
    }
    monkeypatch.setenv("SIM_REPO_ROOT", str(tmp_path))

    policy = ScriptedJointAbsPolicy(
        task_name="table_task_dual_agx_nero",
        sub_task_name="pick_block_color",
        robot_cfg="dual_agx_nero",
        save_observation_images=False,
    )

    action = None
    for _ in range(92):
        action = policy.act(observation)
    assert action["gripper"] == [0.0, 0.0]

    for _ in range(70):
        action = policy.act(observation)
    assert action["gripper"] == [0.1, 0.1]


def test_dual_agx_nero_mount_height_matches_benchmark_table():
    urdf_path = ASSET_ROOT / "robot" / "DualAgxNero" / "urdf" / "dual_agx_nero.urdf"
    root = ET.parse(urdf_path).getroot()

    for joint_name in ("left_mount_joint", "right_mount_joint"):
        joint = root.find(f"joint[@name='{joint_name}']")
        assert joint is not None
        origin = joint.find("origin")
        assert origin is not None
        assert origin.attrib["xyz"].split()[2] == "0.75"

    base_collision = root.find("link[@name='dual_base_link']/collision/geometry/box")
    assert base_collision is not None
    assert base_collision.attrib["size"] == "0.30 1.00 0.75"


def test_dual_agx_nero_usd_contains_table_height_pedestal():
    Usd = pytest.importorskip("pxr.Usd")
    UsdPhysics = pytest.importorskip("pxr.UsdPhysics")

    usd_path = ASSET_ROOT / "robot" / "DualAgxNero" / "dual_agx_nero.usd"
    stage = Usd.Stage.Open(str(usd_path))
    assert stage is not None

    for path in (
        "/dual_agx_nero/dual_base_pedestal",
        "/dual_agx_nero/dual_base_pedestal_collision",
    ):
        prim = stage.GetPrimAtPath(path)
        assert prim.IsValid()
        assert prim.GetTypeName() == "Cube"
        translate = prim.GetAttribute("xformOp:translate").Get()
        scale = prim.GetAttribute("xformOp:scale").Get()
        assert tuple(round(float(value), 3) for value in translate) == (0.0, 0.0, 0.375)
        assert tuple(round(float(value), 3) for value in scale) == (0.3, 1.0, 0.75)

    collision = stage.GetPrimAtPath(
        "/dual_agx_nero/dual_base_pedestal_collision"
    )
    assert collision.HasAPI(UsdPhysics.CollisionAPI)


def test_dual_agx_nero_head_camera_points_down_toward_table():
    Usd = pytest.importorskip("pxr.Usd")
    UsdGeom = pytest.importorskip("pxr.UsdGeom")
    Gf = pytest.importorskip("pxr.Gf")

    usd_path = ASSET_ROOT / "robot" / "DualAgxNero" / "dual_agx_nero.usd"
    stage = Usd.Stage.Open(str(usd_path))
    assert stage is not None

    prim = stage.GetPrimAtPath("/dual_agx_nero/head_front_Camera")
    assert prim.IsValid()
    matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0)
    translation = matrix.ExtractTranslation()
    forward = Gf.Vec3d(-matrix[2][0], -matrix[2][1], -matrix[2][2]).GetNormalized()

    assert tuple(round(float(value), 3) for value in translation) == (0.0, 0.0, 1.5)
    assert forward[0] < -0.85
    assert forward[1] < -0.15
    assert forward[2] < -0.4


def test_dual_agx_nero_imported_base_mesh_matches_pedestal_scale():
    Usd = pytest.importorskip("pxr.Usd")

    for usd_name in ("dual_agx_nero_base.usd", "dual_agx_nero_physics.usd"):
        usd_path = ASSET_ROOT / "robot" / "DualAgxNero" / "configuration" / usd_name
        stage = Usd.Stage.Open(str(usd_path))
        assert stage is not None

        for path in (
            "/visuals/dual_base_link/mesh_0",
            "/colliders/dual_base_link/mesh_0",
        ):
            prim = stage.GetPrimAtPath(path)
            assert prim.IsValid()
            scale = prim.GetAttribute("xformOp:scale").Get()
            assert tuple(round(float(value), 3) for value in scale) == (0.3, 1.0, 0.75)
