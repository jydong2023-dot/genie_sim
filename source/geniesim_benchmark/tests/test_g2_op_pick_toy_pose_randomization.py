import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PACKAGE_ROOT / "scripts" / "generate_g2_op_pick_toy_pose_variants.py"
PROFILE_PATH = (
    PACKAGE_ROOT
    / "scripts"
    / "profiles"
    / "g2_op_pick_toy_blue_block_pose.json"
)
RUN_CONFIG_PATH = (
    PACKAGE_ROOT
    / "src"
    / "geniesim_benchmark"
    / "config"
    / "g2op_robust_g2_op_pick_toy_posegen.yaml"
)

SPEC = importlib.util.spec_from_file_location(
    "g2_op_pick_toy_pose_generator_tested", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)


def _write_source_bundle(task_dir: Path) -> Path:
    source = task_dir / "0"
    source.mkdir(parents=True)
    (source / "scene.usda").write_text(
        '#usda 1.0\n\ndef Xform "World"\n{\n}\n', encoding="utf-8"
    )
    (source / "scene_info.json").write_text(
        json.dumps(
            {
                "layout": {
                    "blue_block": {
                        "description": {"dimensions": [0.09, 0.09, 0.06]},
                        "xyz": [0.04, -0.28, 0.75],
                        "xyzw": [0.0, 0.0, -0.67559, 0.737277],
                    }
                },
                "scene_id": "toy_scene",
            }
        ),
        encoding="utf-8",
    )
    (source / "instructions.json").write_text(
        json.dumps({"instructions": [{"instruction": "pick the blue block"}]}),
        encoding="utf-8",
    )
    (source / "problems.json").write_text(
        json.dumps({"problem1": {"Problem": "g2_op_pick_toy"}}),
        encoding="utf-8",
    )
    return source


def _geometry() -> object:
    return GENERATOR.SceneGeometry(
        target_prim_path="/World/toyscene/Objects/blue_block",
        target_parent_path="/World/toyscene",
        baseline_world_xyz=(0.04, -0.28, 0.75),
        baseline_world_yaw_deg=-85.0,
        parent_world_xyz=(-0.64, -0.008, 0.751),
        parent_world_yaw_deg=-85.0,
        target_planar_radius=0.064,
        support_bounds=GENERATOR.PlanarBounds(-0.55, 0.42, -0.79, 0.66),
        obstacles=(
            GENERATOR.ObstacleBounds(
                "/World/toyscene/Objects/orange",
                GENERATOR.PlanarBounds(-0.05, 0.10, -0.20, -0.05),
            ),
        ),
    )


def _profile() -> object:
    return GENERATOR.PoseProfile(
        target_prim_path="/World/toyscene/Objects/blue_block",
        source_background_usd="background/olalab/home_toy_scene_pick_toy.usda",
        variant_asset_dir="background/olalab/g2_op_pick_toy_pose_variants",
        x_offset_range_m=(-0.03, 0.03),
        y_offset_range_m=(-0.03, 0.03),
        yaw_offset_range_deg=(-30.0, 30.0),
        min_clearance_m=0.01,
        min_planar_offset_m=0.005,
        support_prim_path="/World/toyscene/Objects/table",
        ignore_collision_prim_paths=("/World/toyscene/Objects/table",),
        max_sampling_attempts=1000,
    )


def test_profile_is_task_specific_and_uses_small_relative_offsets():
    profile = GENERATOR.load_profile(PROFILE_PATH)

    assert profile.target_prim_path == "/World/toyscene/Objects/blue_block"
    assert profile.x_offset_range_m == (-0.03, 0.03)
    assert profile.y_offset_range_m == (-0.03, 0.03)
    assert profile.yaw_offset_range_deg == (-30.0, 30.0)
    assert profile.source_background_usd.endswith("home_toy_scene_pick_toy.usda")


def test_posegen_run_config_selects_only_randomized_instances():
    config = yaml.safe_load(RUN_CONFIG_PATH.read_text(encoding="utf-8"))["benchmark"]

    assert config["task_name"] == "g2_op_pick_toy"
    assert config["sub_task_name"] == "g2_op_pick_toy"
    assert config["seed"] == 20260805
    assert config["num_instances"] == 10
    assert config["instance_ids"] == "1,2,3,4,5,6,7,8,9,10"


def test_sampling_is_deterministic_safe_and_relative_to_baseline():
    geometry = _geometry()
    profile = _profile()

    first = GENERATOR.sample_pose_variant(geometry, profile, scenario_seed=123)
    second = GENERATOR.sample_pose_variant(geometry, profile, scenario_seed=123)

    assert first == second
    dx = first.world_xyz[0] - geometry.baseline_world_xyz[0]
    dy = first.world_xyz[1] - geometry.baseline_world_xyz[1]
    assert profile.x_offset_range_m[0] <= dx <= profile.x_offset_range_m[1]
    assert profile.y_offset_range_m[0] <= dy <= profile.y_offset_range_m[1]
    assert math.hypot(dx, dy) >= profile.min_planar_offset_m
    assert (
        profile.yaw_offset_range_deg[0]
        <= first.yaw_offset_deg
        <= profile.yaw_offset_range_deg[1]
    )
    assert first.min_obstacle_clearance_m >= profile.min_clearance_m


def test_world_pose_is_converted_to_target_parent_local_pose():
    geometry = _geometry()

    local_xyz = GENERATOR.world_to_parent_local(
        world_xyz=(0.04, -0.28, 0.75),
        parent_world_xyz=geometry.parent_world_xyz,
        parent_world_yaw_deg=geometry.parent_world_yaw_deg,
    )
    round_trip = GENERATOR.parent_local_to_world(
        local_xyz=local_xyz,
        parent_world_xyz=geometry.parent_world_xyz,
        parent_world_yaw_deg=geometry.parent_world_yaw_deg,
    )

    assert round_trip == pytest.approx((0.04, -0.28, 0.75), abs=1e-9)


def test_generation_writes_background_wrapper_and_synchronized_task_bundle(tmp_path):
    task_dir = tmp_path / "g2_op_pick_toy"
    source = _write_source_bundle(task_dir)
    assets_root = tmp_path / "assets"
    source_background = assets_root / _profile().source_background_usd
    source_background.parent.mkdir(parents=True)
    source_background.write_text(
        '#usda 1.0\n\ndef Xform "World"\n{\n}\n', encoding="utf-8"
    )

    variants = GENERATOR.generate_pose_variants(
        task_dir=task_dir,
        source_instance_dir=source,
        assets_root=assets_root,
        profile=_profile(),
        geometry=_geometry(),
        count=2,
        root_seed=100,
        start_instance_id=1,
    )

    assert [variant.instance_id for variant in variants] == [1, 2]
    for variant in variants:
        instance = task_dir / str(variant.instance_id)
        scenario = json.loads((instance / "scenario.json").read_text())
        scene_info = json.loads((instance / "scene_info.json").read_text())
        wrapper = assets_root / scenario["background_usd"]
        wrapper_text = wrapper.read_text(encoding="utf-8")

        assert scenario["generator"] == GENERATOR.GENERATOR_NAME
        assert scenario["dimension"] == "object_pose"
        assert scenario["scenario_seed"] == 100 + variant.instance_id
        assert scenario["parameters"]["target_prim_path"] == _profile().target_prim_path
        assert scene_info["layout"]["blue_block"]["xyz"] == pytest.approx(
            variant.world_xyz, abs=1e-6
        )
        assert scene_info["layout"]["blue_block"]["xyzw"] == pytest.approx(
            GENERATOR.xyzw_from_yaw_deg(variant.world_yaw_deg), abs=1e-6
        )
        assert 'prepend references = @../home_toy_scene_pick_toy.usda@</World>' in wrapper_text
        assert 'over "blue_block"' in wrapper_text
        assert "xformOp:translate" in wrapper_text
        assert "xformOp:orient" in wrapper_text
        assert (instance / "instructions.json").read_text() == (
            source / "instructions.json"
        ).read_text()
        assert (instance / "problems.json").read_text() == (
            source / "problems.json"
        ).read_text()

    manifest = json.loads((task_dir / "blue_block_pose_manifest.json").read_text())
    assert manifest["generated_instance_ids"] == [1, 2]
    assert manifest["root_seed"] == 100


def test_generation_refuses_to_overwrite_existing_instance(tmp_path):
    task_dir = tmp_path / "g2_op_pick_toy"
    source = _write_source_bundle(task_dir)
    (task_dir / "1").mkdir()
    assets_root = tmp_path / "assets"
    source_background = assets_root / _profile().source_background_usd
    source_background.parent.mkdir(parents=True)
    source_background.write_text("#usda 1.0\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="instance 1"):
        GENERATOR.generate_pose_variants(
            task_dir=task_dir,
            source_instance_dir=source,
            assets_root=assets_root,
            profile=_profile(),
            geometry=_geometry(),
            count=1,
            root_seed=100,
            start_instance_id=1,
        )
