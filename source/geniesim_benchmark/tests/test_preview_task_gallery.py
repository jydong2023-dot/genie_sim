import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from geniesim_benchmark.scripts import preview_task_gallery as gallery


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_iter_task_configs_filters_templates_and_applies_selection(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for name in [
        "config.yaml",
        "template.yaml",
        "teleop.yaml",
        "g2op_if_pick_block_color.yaml",
        "g2op_if_pick_block_shape.yaml",
        "g2op_manip_open_door.yaml",
    ]:
        (config_dir / name).write_text("benchmark: {}\n", encoding="utf-8")

    configs = gallery.iter_task_configs(
        config_dir,
        include=("pick_block",),
        exclude=("shape",),
        limit=1,
    )

    assert [p.name for p in configs] == ["g2op_if_pick_block_color.yaml"]


def test_load_metadata_reads_benchmark_yaml_and_eval_task_json(tmp_path):
    package_root = tmp_path / "geniesim_benchmark"
    config_dir = package_root / "config"
    eval_dir = package_root / "benchmark" / "config" / "eval_tasks"
    config_dir.mkdir(parents=True)
    eval_dir.mkdir(parents=True)

    cfg_path = config_dir / "g2op_if_pick_block_color.yaml"
    _write_yaml(
        cfg_path,
        {
            "benchmark": {
                "task_name": "table_task_1_g2_op",
                "sub_task_name": "pick_block_color",
                "model_arc": "corobot",
            }
        },
    )
    _write_json(
        eval_dir / "table_task_1_g2_op.json",
        {
            "robot": {"robot_cfg": "G2_omnipicker.json", "robot_id": "G2"},
            "scene": {"scene_usd": "background/room/background.usda", "scene_id": "room/workspace"},
        },
    )

    metadata = gallery.load_metadata(cfg_path, config_dir)

    assert metadata["config_name"] == "g2op_if_pick_block_color"
    assert metadata["task_name"] == "table_task_1_g2_op"
    assert metadata["sub_task_name"] == "pick_block_color"
    assert metadata["robot_cfg"] == "G2_omnipicker.json"
    assert metadata["robot_id"] == "G2"
    assert metadata["scene_usd"] == "background/room/background.usda"
    assert metadata["scene_id"] == "room/workspace"


def test_build_preview_command_forces_fast_headless_preview(tmp_path):
    cfg_path = tmp_path / "g2op_if_pick_block_color.yaml"
    output_dir = tmp_path / "out"

    cmd = gallery.build_preview_command(cfg_path, geniesim_bin="geniesim", task_output_dir=output_dir)

    assert cmd == [
        "geniesim",
        "benchmark",
        "run",
        str(cfg_path),
        "--app.headless=true",
        "--benchmark.preview=true",
        "--benchmark.num_episode=1",
        "--benchmark.num_instances=1",
        "--benchmark.enable_vec=0",
        "--benchmark.record=false",
        f"--benchmark.output_dir={output_dir}",
    ]


def test_build_preview_command_can_select_all_numeric_instances(tmp_path):
    cfg_path = tmp_path / "g2op_spatial_stack_red_block_on_black_block.yaml"
    output_dir = tmp_path / "out"

    cmd = gallery.build_preview_command(
        cfg_path,
        geniesim_bin="geniesim",
        task_output_dir=output_dir,
        num_instances=0,
    )

    assert "--benchmark.num_instances=0" in cmd


def test_build_preview_command_can_select_exact_instance_ids(tmp_path):
    cmd = gallery.build_preview_command(
        tmp_path / "task.yaml",
        geniesim_bin="geniesim",
        task_output_dir=tmp_path / "out",
        num_instances=0,
        instance_ids=[8, 9],
    )

    assert "--benchmark.instance_ids=8,9" in cmd


def test_archive_new_preview_images_moves_each_camera_to_task_dir(tmp_path):
    debug_dir = tmp_path / "debug_preview"
    task_dir = tmp_path / "gallery" / "g2op_if_pick_block_color"
    debug_dir.mkdir()
    old = debug_dir / "preview_0000_1000_head.png"
    old.write_bytes(b"old")
    before = gallery.snapshot_preview_images(debug_dir)

    (debug_dir / "preview_0000_2000_head.png").write_bytes(b"head")
    (debug_dir / "preview_0000_2000_left_hand.png").write_bytes(b"left")
    (debug_dir / "preview_0000_2000_right_hand.png").write_bytes(b"right")

    archived = gallery.archive_new_preview_images(debug_dir, before, task_dir)

    assert archived == {
        "head": str(task_dir / "head.png"),
        "left_hand": str(task_dir / "left_hand.png"),
        "right_hand": str(task_dir / "right_hand.png"),
    }
    assert (task_dir / "head.png").read_bytes() == b"head"
    assert (task_dir / "left_hand.png").read_bytes() == b"left"
    assert (task_dir / "right_hand.png").read_bytes() == b"right"
    assert old.exists()


def test_archive_exact_ids_and_build_contact_sheet(tmp_path):
    from PIL import Image

    debug_dir = tmp_path / "debug_preview"
    task_dir = tmp_path / "gallery" / "task"
    debug_dir.mkdir()
    before = gallery.snapshot_preview_images(debug_dir)
    for counter in (0, 1):
        for camera in ("head", "left_hand", "right_hand"):
            Image.new("RGB", (20, 10), (counter * 100, 20, 30)).save(
                debug_dir / f"preview_{counter:04d}_2000_{camera}.png"
            )

    archived = gallery.archive_new_preview_images(
        debug_dir, before, task_dir, instance_ids=[8, 9]
    )
    sheet = gallery.build_contact_sheet(task_dir, [8, 9])

    assert len(archived) == 6
    assert (task_dir / "8" / "head.png").is_file()
    assert (task_dir / "9" / "right_hand.png").is_file()
    assert sheet == task_dir / "contact_sheet.png"
    with Image.open(sheet) as image:
        assert image.size == (60, 80)


def test_run_one_config_sanitizes_python_env_for_geniesim_child(monkeypatch, tmp_path):
    package_root = tmp_path / "geniesim_benchmark"
    config_dir = package_root / "config"
    eval_dir = package_root / "benchmark" / "config" / "eval_tasks"
    output_dir = tmp_path / "gallery"
    debug_dir = tmp_path / "debug_preview"
    repo_root = tmp_path / "repo"
    config_dir.mkdir(parents=True)
    eval_dir.mkdir(parents=True)
    debug_dir.mkdir()
    repo_root.mkdir()

    cfg_path = config_dir / "g1op_s2r_grasp_targets.yaml"
    _write_yaml(cfg_path, {"benchmark": {"task_name": "table_task_1_g1_op", "sub_task_name": "grasp_targets"}})
    _write_json(eval_dir / "table_task_1_g1_op.json", {})

    monkeypatch.setenv("PYTHONPATH", "/isaac-sim/kit/python/lib/python3.11")
    monkeypatch.setenv("PYTHONHOME", "/isaac-sim/kit/python")
    monkeypatch.setenv("GENIESIM_KEEP_ME", "1")
    monkeypatch.setenv("GENIESIM_REPO_ROOT", "/stale/repo")
    monkeypatch.setenv("SIM_REPO_ROOT", "/stale/repo")

    captured = {}

    def fake_run(cmd, env):
        captured["cmd"] = cmd
        captured["env"] = env
        (debug_dir / "preview_0000_2000_head.png").write_bytes(b"head")
        (debug_dir / "preview_0000_2000_left_hand.png").write_bytes(b"left")
        (debug_dir / "preview_0000_2000_right_hand.png").write_bytes(b"right")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gallery.subprocess, "run", fake_run)

    metadata = gallery.run_one_config(
        cfg_path,
        config_dir=config_dir,
        output_dir=output_dir,
        debug_dir=debug_dir,
        repo_root=repo_root,
        geniesim_bin="geniesim",
    )

    assert metadata["status"] == "ok"
    assert "PYTHONPATH" not in captured["env"]
    assert "PYTHONHOME" not in captured["env"]
    assert captured["env"]["GENIESIM_KEEP_ME"] == "1"
    assert captured["env"]["GENIESIM_REPO_ROOT"] == str(repo_root)
    assert captured["env"]["SIM_REPO_ROOT"] == str(repo_root)


def test_discover_repo_root_falls_back_to_checkout_root_from_package(monkeypatch, tmp_path):
    repo = tmp_path / "genie_sim"
    package = repo / "source" / "geniesim_benchmark" / "src" / "geniesim_benchmark"
    package.mkdir(parents=True)
    monkeypatch.delenv("GENIESIM_REPO_ROOT", raising=False)
    monkeypatch.delenv("SIM_REPO_ROOT", raising=False)
    monkeypatch.setattr(gallery, "package_root", lambda: package)

    assert gallery.discover_repo_root(start=tmp_path / "elsewhere") == repo
