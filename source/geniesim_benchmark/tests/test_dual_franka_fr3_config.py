import json
import importlib.util
from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src" / "geniesim_benchmark"
ROBOT_MODULE_PATH = SRC_ROOT / "app" / "utils" / "robot.py"

spec = importlib.util.spec_from_file_location("geniesim_robot_cfg", ROBOT_MODULE_PATH)
robot_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(robot_module)
RobotCfg = robot_module.RobotCfg


def _minimal_robot_cfg(robot_generation: str = "dual_franka") -> dict:
    return {
        "camera": {
            "/dual_franka_fr3/head_front_Camera": [640, 400, 30],
        },
        "gripper": {
            "closed_velocities": {"left": [-0.04], "right": [-0.04]},
            "end_effector_name": {"left": "left_fr3_tcp", "right": "right_fr3_tcp"},
            "end_effector_prim_path": {
                "left": "/dual_franka_fr3/left_fr3/fr3_hand_tcp",
                "right": "/dual_franka_fr3/right_fr3/fr3_hand_tcp",
            },
            "finger_names": {
                "left": ["left_fr3_finger_joint1", "left_fr3_finger_joint2"],
                "right": ["right_fr3_finger_joint1", "right_fr3_finger_joint2"],
            },
            "gripper_control_joint": {
                "left": "/dual_franka_fr3/left_fr3/fr3_hand/fr3_finger_joint1",
                "right": "/dual_franka_fr3/right_fr3/fr3_hand/fr3_finger_joint1",
            },
            "gripper_name": {"left": "franka_hand", "right": "franka_hand"},
            "gripper_type": "linear",
            "max_force": -1,
            "opened_positions": {"left": [0.04], "right": [0.04]},
        },
        "robot": {
            "arm": "dual",
            "base_prim_path": "/dual_franka_fr3",
            "dof_nums": 18,
            "initial_position": [],
            "joint_delta_time": 0.01,
            "lock_joints": [],
            "robot_generation": robot_generation,
            "robot_name": "dual_franka_fr3",
            "robot_usd": "robot/DualFrankaFR3/robot.usd",
            "urdf_name": "",
        },
    }


def test_robot_cfg_accepts_explicit_non_g1_g2_generation(tmp_path):
    cfg_path = tmp_path / "dual_franka_fr3.json"
    cfg_path.write_text(json.dumps(_minimal_robot_cfg()), encoding="utf-8")

    robot = RobotCfg(str(cfg_path))

    assert robot.robot_name == "dual_franka_fr3"
    assert robot.robot_generation == "dual_franka"
    assert robot.robot_prim_path == "/dual_franka_fr3"
    assert robot.arm_type == "dual"
    assert robot.robot_usd == "robot/DualFrankaFR3/robot.usd"


def test_dual_franka_fr3_benchmark_configs_are_wired():
    robot_cfg_path = SRC_ROOT / "app" / "robot_cfg" / "dual_franka_fr3.json"
    eval_task_path = (
        SRC_ROOT / "benchmark" / "config" / "eval_tasks" / "table_task_dual_franka_fr3.json"
    )
    run_cfg_path = SRC_ROOT / "config" / "dual_franka_fr3_if_pick_block_color.yaml"

    robot_cfg = json.loads(robot_cfg_path.read_text(encoding="utf-8"))
    eval_task = json.loads(eval_task_path.read_text(encoding="utf-8"))
    run_cfg = yaml.safe_load(run_cfg_path.read_text(encoding="utf-8"))

    assert robot_cfg["robot"]["robot_name"] == "dual_franka_fr3"
    assert robot_cfg["robot"]["robot_generation"] == "dual_franka"
    assert robot_cfg["robot"]["robot_usd"] == "robot/DualFrankaFR3/robot.usd"
    assert robot_cfg["camera"]["/dual_franka_fr3/head_front_Camera"] == [640, 400, 30]

    assert eval_task["robot"]["robot_cfg"] == "dual_franka_fr3.json"
    assert eval_task["robot"]["robot_id"] == "dual_franka_fr3"
    assert eval_task["recording_setting"]["camera_list"] == [
        "/dual_franka_fr3/head_front_Camera"
    ]

    assert run_cfg["benchmark"]["task_name"] == "table_task_dual_franka_fr3"
    assert run_cfg["benchmark"]["sub_task_name"] == "pick_block_color"


def test_dual_franka_fr3_runtime_mappings_are_available():
    from geniesim_benchmark.benchmark.config.robot_init_states import TASK_INFO_DICT
    from geniesim_benchmark.utils.infer_pre_process import TaskInfo
    from geniesim_benchmark.utils.name_utils import ROBOT_CONFIGS, robot_type_mapping

    assert robot_type_mapping("dual_franka_fr3") == "dual_franka_fr3"

    cfg = ROBOT_CONFIGS["dual_franka_fr3"]
    assert len(cfg["left_arm_joints"]) == 7
    assert len(cfg["right_arm_joints"]) == 7
    assert cfg["arm_joints"] == cfg["left_arm_joints"] + cfg["right_arm_joints"]
    assert cfg["gripper_joints"] == ["left_fr3_finger_joint1", "right_fr3_finger_joint1"]

    task_info_cfg = TASK_INFO_DICT["pick_block_color"]["dual_franka_fr3"]
    init_arm, init_head, init_waist, _init_hand, init_gripper = TaskInfo(
        task_info_cfg, "dual_franka_fr3"
    ).init_pose()

    assert len(init_arm) == 14
    assert init_head == []
    assert init_waist == []
    assert init_gripper == [0.04, 0.04]


def test_robot_tf_registration_has_generic_root_fallback():
    robot_interface_path = SRC_ROOT / "app" / "ros_publisher" / "robot_interface.py"
    source = robot_interface_path.read_text(encoding="utf-8")

    assert "base_link_prim = stage.GetPrimAtPath" in source
    assert "if not base_link_prim.IsValid()" in source
    assert "stage.GetPrimAtPath(f\"/{robot_ns}\")" in source
    assert "self.build_tf_tree(stage, base_link_prim, None, None)" in source
