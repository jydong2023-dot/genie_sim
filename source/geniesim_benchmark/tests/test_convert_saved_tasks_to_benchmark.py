import importlib.util
import json
import math
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PACKAGE_ROOT / "scripts" / "convert_saved_tasks_to_benchmark.py"
SPEC = importlib.util.spec_from_file_location("convert_saved_tasks_to_benchmark", SCRIPT_PATH)
converter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(converter)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _make_asset(
    asset_dir: Path,
    semantic_name: str,
    size: list[float],
    entity_quaternion: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
) -> None:
    asset_dir.mkdir(parents=True)
    (asset_dir / "Aligned.usd").write_text("#usda 1.0\n", encoding="utf-8")
    quaternion_text = ", ".join(str(value) for value in entity_quaternion)
    (asset_dir / "Aligned.usda").write_text(
        "#usda 1.0\n"
        'def Xform "World"\n'
        "{\n"
        '    def Xform "entity" (\n'
        "        prepend payload = @Aligned.usd@\n"
        "    )\n"
        "    {\n"
        f"        quatf xformOp:orient = ({quaternion_text})\n"
        '        uniform token[] xformOpOrder = ["xformOp:orient"]\n'
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    (asset_dir / "description.py").write_text(
        repr({"semantic_name": [semantic_name], "object_category": ["test object"]}),
        encoding="utf-8",
    )
    _write_json(
        asset_dir / "object_parameters.json",
        {"semantic_name": semantic_name, "size": size, "unit": "m"},
    )


def _make_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    assets_root = tmp_path / "geniesim_assets"
    table_dir = assets_root / "objects/benchmark/table/benchmark_table_019"
    _make_asset(table_dir, "table", [0.6, 1.0, 0.73])
    (table_dir / "item.py").write_text(
        repr(
            {
                "shapes": [
                    {
                        "name": "bbox",
                        "position": [0.0, 0.0, 0.1],
                        "size": [0.6, 1.0, 0.73],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    target_dir = assets_root / "objects/benchmark/beverage_bottle/target"
    other_dir = assets_root / "objects/benchmark/lemon/other"
    wrapper_rotation = (math.sqrt(0.5), math.sqrt(0.5), 0.0, 0.0)
    _make_asset(target_dir, "can", [0.06, 0.12, 0.06], wrapper_rotation)
    _make_asset(other_dir, "fruit", [0.08, 0.08, 0.08], wrapper_rotation)

    input_dir = tmp_path / "saved_task"
    input_dir.mkdir()
    common = {
        "scene_usd": "background/home/home_b_with_table/background.usda",
        "task_name": "straighten_and_place_beverage_g2",
        "objects": [
            {
                "object_id": converter.DEFAULT_TARGET_ID,
                "data_info_dir": "/geniesim_assets/objects/benchmark/beverage_bottle/target/",
                "english_semantic_name": "fanta",
                "position": [2.92, 0.77, 0.85],
                "quaternion": [1.0, 0.0, 0.0, 0.0],
                "size": [0.06, 0.12, 0.06],
                "mass": 0.05,
                "scale": 1,
            },
            {
                "object_id": "other_object",
                "data_info_dir": "/geniesim_assets/objects/benchmark/lemon/other/",
                "english_semantic_name": "lemon",
                "position": [2.91, 0.5, 0.86],
                "quaternion": [1.0, 0.0, 0.0, 0.0],
                "size": [0.08, 0.08, 0.08],
                "mass": 0.05,
                "scale": 1,
            },
        ],
        "task_metric": {
            "filter_rules": [
                {"rule_name": "is_gripper_in_view", "params": {"gripper": "left"}},
                {
                    "rule_name": "is_object_end_pose_up",
                    "params": {
                        "objects": [converter.DEFAULT_TARGET_ID],
                        "objects_up_axis": ["y"],
                        "thresholds": [0.2],
                    },
                },
            ]
        },
    }
    _write_json(input_dir / "task_0.json", common)
    second = json.loads(json.dumps(common))
    second["objects"][0]["position"] = [2.92, 0.7, 0.85]
    _write_json(input_dir / "task_1.json", second)

    template = tmp_path / "template.json"
    _write_json(template, {"origin": {"position": [2.91, 0.76, 0.0], "quaternion": [1, 0, 0, 0]}})
    return assets_root, input_dir, template, tmp_path / "output"


def test_world_to_local_pose_applies_origin_rotation():
    half_sqrt = math.sqrt(0.5)
    position, quaternion = converter.world_to_local_pose(
        [1.0, 0.0, 0.0],
        [half_sqrt, 0.0, 0.0, half_sqrt],
        [0.0, 0.0, 0.0],
        [half_sqrt, 0.0, 0.0, half_sqrt],
    )

    assert position == pytest.approx((0.0, -1.0, 0.0))
    assert quaternion == pytest.approx((1.0, 0.0, 0.0, 0.0))


def test_wrapper_compensation_preserves_composed_rigid_body_pose(tmp_path):
    asset_dir = tmp_path / "asset"
    half_sqrt = math.sqrt(0.5)
    _make_asset(asset_dir, "can", [0.06, 0.12, 0.06], (half_sqrt, half_sqrt, 0.0, 0.0))
    source_quaternion = converter.normalize_quaternion((0.86, 0.0, 0.0, -0.51))

    parent, entity = converter.compensate_asset_wrapper_pose(
        source_quaternion, asset_dir / "Aligned.usda"
    )
    composed = converter.normalize_quaternion(converter.quaternion_multiply(parent, entity))

    assert composed == pytest.approx(source_quaternion)
    world_y = converter.rotate_vector(composed, (0.0, 1.0, 0.0))
    assert world_y[2] == pytest.approx(0.0)


def test_main_batch_converts_contract_and_semantics(tmp_path):
    assets_root, input_dir, template, output_dir = _make_fixture(tmp_path)

    assert converter.main(
        [
            "--input-dir",
            str(input_dir),
            "--output-task-dir",
            str(output_dir),
            "--source-template",
            str(template),
            "--assets-root",
            str(assets_root),
            "--start-instance",
            "50",
        ]
    ) == 0

    assert {path.name for path in (output_dir / "50").iterdir()} == {
        "scene.usda",
        "scene_info.json",
        "instructions.json",
        "problems.json",
    }
    scene_text = (output_dir / "50/scene.usda").read_text(encoding="utf-8")
    assert "prepend payload = @/geniesim_assets/objects/benchmark/beverage_bottle/target/Aligned.usda@" in scene_text
    assert "float physics:mass = 0.05" in scene_text
    assert "double3 xformOp:translate = (0.01, 0.01, 0.85)" in scene_text
    assert "quatf xformOp:orient = (0.707106781187, -0.707106781187, 0, 0)" in scene_text

    instructions = json.loads((output_dir / "50/instructions.json").read_text(encoding="utf-8"))
    assert instructions["instructions"][0]["instruction"].startswith("Left arm picks up the Fanta")
    problems = json.loads((output_dir / "50/problems.json").read_text(encoding="utf-8"))
    action_list = problems["problem1"]["Acts"][0]["ActionList"]
    assert action_list[0]["ActionSetWaitAny"][0]["Follow"].endswith("|left_gripper")
    threshold = float(action_list[1]["ActionSetWaitAny"][0]["Upright"].split("|")[1])
    assert threshold == pytest.approx(math.degrees(0.2))

    scene_info = json.loads((output_dir / "50/scene_info.json").read_text(encoding="utf-8"))
    target = scene_info["layout"][converter.DEFAULT_TARGET_ID]
    assert target["xyz"] == pytest.approx([0.01, 0.01, 0.85])
    assert target["xyzw"] == pytest.approx([-0.707107, 0.0, 0.0, 0.707107])
    assert (output_dir / "conversion_manifest_50_51.json").is_file()
    manifest = json.loads((output_dir / "conversion_manifest_50_51.json").read_text(encoding="utf-8"))
    assert manifest["records"][0]["unsupported_filter_rules"] == ["is_gripper_in_view"]
    assert manifest["records"][0]["target_source_quaternion_wxyz"] == pytest.approx(
        [1.0, 0.0, 0.0, 0.0]
    )
    assert manifest["records"][1]["arm"] == "right"


def test_auto_numbering_and_overwrite_protection(tmp_path):
    assets_root, input_dir, template, output_dir = _make_fixture(tmp_path)
    (output_dir / "0").mkdir(parents=True)
    (output_dir / "2").mkdir()
    common = [
        "--input-dir",
        str(input_dir),
        "--output-task-dir",
        str(output_dir),
        "--source-template",
        str(template),
        "--assets-root",
        str(assets_root),
    ]

    assert converter.main([*common, "--dry-run"]) == 0
    assert not (output_dir / "3").exists()
    assert converter.main(common) == 0
    assert (output_dir / "3/scene.usda").is_file()
    assert (output_dir / "4/scene.usda").is_file()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        converter.main([*common, "--start-instance", "3"])
