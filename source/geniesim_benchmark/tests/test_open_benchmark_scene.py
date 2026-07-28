import json
from pathlib import Path

import yaml

from geniesim_benchmark.scripts import open_benchmark_scene as viewer


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_scene_selection_resolves_benchmark_scene_paths(tmp_path):
    package_root = tmp_path / "geniesim_benchmark"
    config_dir = package_root / "config"
    eval_dir = package_root / "benchmark" / "config" / "eval_tasks"
    robot_dir = package_root / "app" / "robot_cfg"
    llm_dir = package_root / "benchmark" / "config" / "llm_task" / "pick_block_color" / "3"
    config_dir.mkdir(parents=True)
    eval_dir.mkdir(parents=True)
    robot_dir.mkdir(parents=True)
    llm_dir.mkdir(parents=True)
    (llm_dir / "scene.usda").write_text("#usda 1.0\n", encoding="utf-8")

    cfg_path = config_dir / "g2op_if_pick_block_color.yaml"
    _write_yaml(
        cfg_path,
        {
            "benchmark": {
                "task_name": "table_task_1_g2_op",
                "sub_task_name": "pick_block_color",
            }
        },
    )
    _write_json(
        eval_dir / "table_task_1_g2_op.json",
        {
            "robot": {
                "robot_cfg": "G2_omnipicker.json",
                "robot_init_pose": {
                    "workspace_00": {
                        "position": [-0.71, 0.0, 0.0],
                        "quaternion": [1.0, 0.0, 0.0, 0.0],
                    }
                },
            },
            "scene": {
                "scene_id": "gm_supermarket_01/workspace_00",
                "scene_usd": "/background/home/home_b_aligned/background.usda",
            },
        },
    )
    _write_json(
        robot_dir / "G2_omnipicker.json",
        {
            "robot": {
                "base_prim_path": "/genie",
                "robot_name": "G2_omnipicker",
                "robot_usd": "robot/G2_omnipicker/robot_fix.usda",
            }
        },
    )

    selection = viewer.load_scene_selection(
        cfg_path,
        config_dir=config_dir,
        assets_root=Path("/geniesim_assets"),
        instance_id=3,
    )

    assert selection.config_name == "g2op_if_pick_block_color"
    assert selection.task_name == "table_task_1_g2_op"
    assert selection.sub_task_name == "pick_block_color"
    assert selection.robot_cfg == "G2_omnipicker.json"
    assert selection.robot_name == "G2_omnipicker"
    assert selection.robot_prim_path == "/genie"
    assert selection.robot_usd_path == Path("/geniesim_assets/robot/G2_omnipicker/robot_fix.usda")
    assert selection.scene_usd_path == Path("/geniesim_assets/background/home/home_b_aligned/background.usda")
    assert selection.workspace_usd_path == llm_dir / "scene.usda"
    assert selection.robot_position == [-0.71, 0.0, 0.0]
    assert selection.robot_quaternion == [1.0, 0.0, 0.0, 0.0]


def test_resolve_config_path_accepts_unique_substrings(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "g2op_if_pick_block_color.yaml").write_text("benchmark: {}\n", encoding="utf-8")
    (config_dir / "g2op_if_pick_block_shape.yaml").write_text("benchmark: {}\n", encoding="utf-8")

    assert viewer.resolve_config_path("pick_block_color", config_dir) == (
        config_dir / "g2op_if_pick_block_color.yaml"
    ).resolve()


def test_build_docker_exec_command_uses_container_isaac_sim(tmp_path):
    script = Path("/workspace/source/geniesim_benchmark/scripts/open_benchmark_scene.bash")
    cmd = viewer.build_docker_exec_command(
        script,
        container="geniesim3",
        uid=1000,
        gid=1000,
        args=["--config", "g2op_if_pick_block_color"],
    )

    assert cmd == [
        "docker",
        "exec",
        "-it",
        "-u",
        "1000:1000",
        "-e",
        "HOME=/home/isaac-sim",
        "-e",
        "SIM_REPO_ROOT=/workspace",
        "-e",
        "GENIESIM_REPO_ROOT=/workspace",
        "-e",
        "GENIESIM_ASSETS_PATH=/geniesim_assets",
        "-w",
        "/workspace",
        "geniesim3",
        str(script),
        "--config",
        "g2op_if_pick_block_color",
    ]


def test_isaacsim_numpy_library_paths_find_kit_and_pip_archive_dirs(tmp_path):
    isaac_root = tmp_path / "isaac-sim"
    kit_numpy_libs = isaac_root / "kit" / "python" / "lib" / "python3.11" / "site-packages" / "numpy.libs"
    pip_numpy_libs = (
        isaac_root
        / "extscache"
        / "omni.kit.pip_archive-0.0.0+test.lx64.cp311"
        / "pip_prebundle"
        / "numpy.libs"
    )
    kit_numpy_libs.mkdir(parents=True)
    pip_numpy_libs.mkdir(parents=True)

    paths = viewer.isaacsim_numpy_library_paths(isaac_root)

    assert paths == [pip_numpy_libs, kit_numpy_libs]


def test_prepend_library_paths_preserves_existing_and_avoids_duplicates(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    env = {"LD_LIBRARY_PATH": f"{second}:/old"}

    updated = viewer.prepend_library_paths(env, [first, second])

    assert updated["LD_LIBRARY_PATH"] == f"{first}:{second}:/old"


def test_prepare_isaacsim_numpy_runtime_env_marks_ready_after_prepend(tmp_path):
    isaac_root = tmp_path / "isaac-sim"
    numpy_libs = isaac_root / "kit" / "python" / "lib" / "python3.11" / "site-packages" / "numpy.libs"
    numpy_libs.mkdir(parents=True)

    updated = viewer.prepare_isaacsim_numpy_runtime_env({}, isaac_root=isaac_root)

    assert updated["LD_LIBRARY_PATH"] == str(numpy_libs)
    assert updated["GENIESIM_NUMPY_LIBS_READY"] == "1"


def test_enable_isaac_extension_invokes_injected_enabler():
    enabled = []

    viewer.enable_isaac_extension("omni.physx.supportui", enable_extension=enabled.append)

    assert enabled == ["omni.physx.supportui"]


def test_prepare_workspace_usd_rewrites_container_asset_prefix(tmp_path):
    source = tmp_path / "scene.usda"
    source.write_text(
        '#usda 1.0\nprepend payload = @/geniesim_assets/objects/foo/Aligned.usda@\n',
        encoding="utf-8",
    )
    out_dir = tmp_path / "prepared"

    prepared = viewer.prepare_workspace_usd(
        source,
        assets_root=Path("/home/user/djy/geniesim_assets"),
        output_dir=out_dir,
    )

    assert prepared == out_dir / "scene.usda"
    assert "@/home/user/djy/geniesim_assets/objects/foo/Aligned.usda@" in prepared.read_text(
        encoding="utf-8"
    )
