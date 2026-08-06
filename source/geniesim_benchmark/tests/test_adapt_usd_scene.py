import importlib.util
import json
from pathlib import Path

import pytest
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PACKAGE_ROOT / "scripts" / "adapt_usd_scene.py"
SPEC = importlib.util.spec_from_file_location("adapt_usd_scene", SCRIPT_PATH)
adapter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(adapter)


def _make_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    assets_root = tmp_path / "geniesim_assets"
    scene = assets_root / "background" / "robosnap" / "demo_scene.usd"
    scene.parent.mkdir(parents=True)
    scene.write_text("#usda 1.0\n", encoding="utf-8")

    robot_config_dir = tmp_path / "robot_cfg"
    robot_config_dir.mkdir()
    (robot_config_dir / "dual_agx_nero.json").write_text(
        json.dumps(
            {
                "robot": {"arm": "dual"},
                "camera": {
                    "/dual_agx_nero/head_front_Camera": [640, 400, 30],
                    "/dual_agx_nero/left_gripper_base/Left_Camera": [640, 400, 30],
                },
            }
        ),
        encoding="utf-8",
    )
    return assets_root, scene, robot_config_dir


def test_infers_assets_root_and_builds_matching_workspace_contract(tmp_path):
    assets_root, scene, robot_config_dir = _make_fixture(tmp_path)

    assert adapter.infer_assets_root(scene) == assets_root
    relative_scene = adapter.validate_scene(scene, assets_root)
    robot_config = adapter.load_robot_config("dual_agx_nero.json", robot_config_dir)
    cameras = adapter.resolve_cameras(robot_config, None)
    run_config, eval_task = adapter.build_configs(
        relative_scene=relative_scene,
        task_name="table_task_dual_agx_nero_demo",
        task_type="demo_debug",
        platform="dual_agx_nero",
        robot_id="dual_agx_nero",
        robot_cfg="dual_agx_nero.json",
        robot_arm="dual",
        cameras=cameras,
        workspace_id="workspace_00",
        robot_position=[-0.71, 0.0, 0.0],
        robot_quaternion=[1.0, 0.0, 0.0, 0.0],
        workspace_position=[0.0, 0.0, 0.75],
        workspace_quaternion=[1.0, 0.0, 0.0, 0.0],
        workspace_size=[0.0, 0.0, 0.0],
        base_task="table_task_1_g2_op",
    )
    adapter.validate_generated_configs(run_config, eval_task)

    assert eval_task["scene"]["scene_usd"] == "/background/robosnap/demo_scene.usd"
    assert eval_task["scene"]["scene_info_dir"] == "/background/robosnap/"
    assert eval_task["scene"]["scene_id"] == "robosnap/demo_scene/workspace_00"
    assert adapter._scene_name(relative_scene) == "robosnap/demo_scene"
    assert "workspace_00" in eval_task["scene"]["function_space_objects"]
    assert "workspace_00" in eval_task["robot"]["robot_init_pose"]
    assert run_config["benchmark"]["keep_open"] is True
    assert run_config["benchmark"]["policy_class"] == "DemoPolicy"


def test_main_writes_parseable_yaml_and_json(tmp_path):
    assets_root, scene, robot_config_dir = _make_fixture(tmp_path)
    config_dir = tmp_path / "config"
    eval_dir = tmp_path / "eval_tasks"

    result = adapter.main(
        [
            "--scene-usd",
            str(scene),
            "--assets-root",
            str(assets_root),
            "--robot-config-dir",
            str(robot_config_dir),
            "--config-dir",
            str(config_dir),
            "--eval-task-dir",
            str(eval_dir),
            "--task-name",
            "table_task_dual_agx_nero_demo",
            "--config-name",
            "dual_agx_nero_demo_debug",
        ]
    )

    assert result == 0
    run_config = yaml.safe_load((config_dir / "dual_agx_nero_demo_debug.yaml").read_text(encoding="utf-8"))
    eval_task = json.loads((eval_dir / "table_task_dual_agx_nero_demo.json").read_text(encoding="utf-8"))
    assert run_config["benchmark"]["task_name"] == "table_task_dual_agx_nero_demo"
    assert eval_task["recording_setting"]["camera_list"] == list(
        json.loads((robot_config_dir / "dual_agx_nero.json").read_text(encoding="utf-8"))["camera"]
    )


def test_main_refuses_to_overwrite_without_force(tmp_path):
    assets_root, scene, robot_config_dir = _make_fixture(tmp_path)
    config_dir = tmp_path / "config"
    eval_dir = tmp_path / "eval_tasks"
    common_args = [
        "--scene-usd",
        str(scene),
        "--assets-root",
        str(assets_root),
        "--robot-config-dir",
        str(robot_config_dir),
        "--config-dir",
        str(config_dir),
        "--eval-task-dir",
        str(eval_dir),
    ]

    assert adapter.main(common_args) == 0
    assert (config_dir / "dual_agx_nero_robosnap_demo_scene_debug.yaml").is_file()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        adapter.main(common_args)
    assert adapter.main([*common_args, "--force"]) == 0


def test_dry_run_does_not_write_files(tmp_path, capsys):
    assets_root, scene, robot_config_dir = _make_fixture(tmp_path)
    config_dir = tmp_path / "config"
    eval_dir = tmp_path / "eval_tasks"

    assert (
        adapter.main(
            [
                "--scene-usd",
                str(scene),
                "--assets-root",
                str(assets_root),
                "--robot-config-dir",
                str(robot_config_dir),
                "--config-dir",
                str(config_dir),
                "--eval-task-dir",
                str(eval_dir),
                "--dry-run",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "# YAML:" in output
    assert "# JSON:" in output
    assert not config_dir.exists()
    assert not eval_dir.exists()


def test_rejects_camera_missing_from_robot_config(tmp_path):
    _, _, robot_config_dir = _make_fixture(tmp_path)
    robot_config = adapter.load_robot_config("dual_agx_nero.json", robot_config_dir)

    with pytest.raises(ValueError, match="missing from the robot config"):
        adapter.resolve_cameras(robot_config, ["/dual_agx_nero/Unknown_Camera"])
