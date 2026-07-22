import json
import importlib.util
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PACKAGE_ROOT / "scripts" / "scenario_augmentation.py"
SPEC = importlib.util.spec_from_file_location("scenario_augmentation_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)

CLI_PATH = PACKAGE_ROOT / "scripts" / "generate_task_scenarios.py"
CLI_SPEC = importlib.util.spec_from_file_location("generate_task_scenarios_tested", CLI_PATH)
assert CLI_SPEC is not None and CLI_SPEC.loader is not None
CLI = importlib.util.module_from_spec(CLI_SPEC)
sys.modules[CLI_SPEC.name] = CLI
CLI_SPEC.loader.exec_module(CLI)

AugmentationProfile = GENERATOR.AugmentationProfile
build_generic_scenario_specs = GENERATOR.build_generic_scenario_specs
describe_scene = GENERATOR.describe_scene
generate_augmented_scenarios = GENERATOR.generate_augmented_scenarios
load_profile = GENERATOR.load_profile
load_scene_info = GENERATOR.load_scene_info


BASE_SCENE = '''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def "World"
{
    def "Objects"
    {
        def Xform "table_001"
        {
            double3 xformOp:translate = (0, 0, 0.3)
            uniform token[] xformOpOrder = ["xformOp:translate"]
        }
        def Xform "apple_001"
        {
            quatf xformOp:orient = (1, 0, 0, 0)
            double3 xformOp:translate = (-0.1, 0.1, 0.9)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]
        }
        def Xform "bowl_001"
        {
            quatf xformOp:orient = (1, 0, 0, 0)
            double3 xformOp:translate = (0.1, -0.1, 0.9)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]
        }
    }
}
'''


def _entry(category, xyz, color):
    return {
        "description": {
            "color": color,
            "object_category": category,
            "semantic_name": category,
        },
        "keywords": category,
        "tags": [],
        "xyz": xyz,
        "xyzw": [0.0, 0.0, 0.0, 1.0],
    }


def _write_source(root: Path) -> Path:
    source = root / "arbitrary_task" / "7"
    source.mkdir(parents=True)
    (source / "scene.usda").write_text(BASE_SCENE, encoding="utf-8")
    (source / "scene_info.json").write_text(
        json.dumps(
            {
                "layout": {
                    "table_001": _entry(["furniture", "table"], [0, 0, 0.3], "white"),
                    "apple_001": _entry(["food", "fruit"], [-0.1, 0.1, 0.9], "red"),
                    "bowl_001": _entry(["container", "bowl"], [0.1, -0.1, 0.9], "blue"),
                },
                "relations": {"graph": {"nodes": [], "links": []}},
                "scene_id": "arbitrary_scene",
                "seed": 10,
            }
        ),
        encoding="utf-8",
    )
    (source / "instructions.json").write_text(
        json.dumps({"instructions": [{"instruction": "put the apple in the bowl"}]}),
        encoding="utf-8",
    )
    (source / "problems.json").write_text(
        json.dumps({"problem1": {"Problem": "put_apple_in_bowl"}}), encoding="utf-8"
    )
    (source / "notes.txt").write_text("preserve arbitrary bundle files\n", encoding="utf-8")
    return source


def test_discovers_table_and_movable_objects_from_scene_info(tmp_path):
    source = _write_source(tmp_path)

    discovered = describe_scene(source)

    assert discovered["table_ids"] == ["table_001"]
    assert discovered["movable_object_ids"] == ["apple_001", "bowl_001"]
    assert discovered["move_with_table_ids"] == ["apple_001", "bowl_001"]


def test_builds_deterministic_dimension_cycle(tmp_path):
    source = _write_source(tmp_path)
    scene_info = load_scene_info(source)
    profile = AugmentationProfile()

    specs = build_generic_scenario_specs(scene_info, count=6, seed=1234, profile=profile)

    assert [spec.dimension for spec in specs] == [
        "baseline",
        "object_pose",
        "lighting",
        "table_height",
        "table_appearance",
        "combined",
    ]
    assert specs == build_generic_scenario_specs(scene_info, 6, 1234, profile)
    assert specs != build_generic_scenario_specs(scene_info, 6, 1235, profile)


def test_generates_portable_overrides_and_preserves_task_semantics(tmp_path):
    source = _write_source(tmp_path)
    output = tmp_path / "arbitrary_task_augmented"

    generate_augmented_scenarios(source, output, count=6, seed=1234)

    for instance_id in range(6):
        instance = output / str(instance_id)
        assert (instance / "scene.usda").is_file()
        assert (instance / "scene_source.usda").read_text(encoding="utf-8") == BASE_SCENE
        assert (instance / "notes.txt").read_text(encoding="utf-8").startswith("preserve")
        assert json.loads((instance / "instructions.json").read_text())[
            "instructions"
        ][0]["instruction"] == "put the apple in the bowl"
        assert json.loads((instance / "problems.json").read_text())["problem1"][
            "Problem"
        ] == "put_apple_in_bowl"

    pose_scene = (output / "1" / "scene.usda").read_text(encoding="utf-8")
    assert "subLayers = [@./scene_source.usda@]" in pose_scene
    assert 'over "apple_001"' in pose_scene
    assert "xformOp:translate" in pose_scene
    assert "xformOp:orient" in pose_scene

    light_scenario = json.loads((output / "2" / "scenario.json").read_text())
    assert light_scenario["light_config"]["temperature"] > 0
    assert light_scenario["light_config"]["intensity"] >= 0

    appearance_scene = (output / "4" / "scene.usda").read_text(encoding="utf-8")
    assert "TableAugmentationMaterial" in appearance_scene
    assert 'bindMaterialAs = "strongerThanDescendants"' in appearance_scene


def test_table_height_and_metadata_move_together(tmp_path):
    source = _write_source(tmp_path)
    output = tmp_path / "output"
    profile = AugmentationProfile.from_dict(
        {
            "include_baseline": False,
            "dimensions": ["table_height"],
            "table_height": {"offsets": [0.05]},
        }
    )

    generate_augmented_scenarios(source, output, count=1, seed=11, profile=profile)

    info = json.loads((output / "0" / "scene_info.json").read_text())
    scene = (output / "0" / "scene.usda").read_text(encoding="utf-8")
    assert info["layout"]["table_001"]["xyz"][2] == pytest.approx(0.35)
    assert info["layout"]["apple_001"]["xyz"][2] == pytest.approx(0.95)
    assert info["layout"]["bowl_001"]["xyz"][2] == pytest.approx(0.95)
    assert "(0, 0, 0.35)" in scene
    assert scene.count("0.95)") == 2


def test_texture_profile_copies_asset_and_updates_metadata(tmp_path):
    source = _write_source(tmp_path)
    texture = tmp_path / "wood.png"
    texture.write_bytes(b"synthetic texture payload")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "include_baseline": False,
                "dimensions": ["table_appearance"],
                "table_appearance": {
                    "colors": [[0.4, 0.2, 0.1]],
                    "textures": ["wood.png"],
                    "roughness": [0.6],
                },
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "output"
    generate_augmented_scenarios(
        source, output, count=1, profile=load_profile(profile_path)
    )

    assert (output / "0" / "augmentation_assets" / "wood.png").read_bytes() == texture.read_bytes()
    scene = (output / "0" / "scene.usda").read_text(encoding="utf-8")
    assert "UsdUVTexture" in scene
    assert "@./augmentation_assets/wood.png@" in scene
    metadata = json.loads((output / "0" / "scene_info.json").read_text())
    material = metadata["layout"]["table_001"]["description"][
        "augmentation_material"
    ]
    assert material["texture"] == "./augmentation_assets/wood.png"


def test_in_place_replacement_stages_source_before_clearing(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    source = _write_source(tmp_path)
    source.replace(task / "0")

    generate_augmented_scenarios(
        task / "0", task, count=2, seed=5, replace_generated=True
    )

    assert (task / "0" / "scene_source.usda").read_text(encoding="utf-8") == BASE_SCENE
    assert (task / "1" / "instructions.json").is_file()


def test_in_place_append_starts_after_highest_numeric_directory(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    source = _write_source(tmp_path)
    source.replace(task / "0")
    (task / "7").mkdir()

    specs = generate_augmented_scenarios(task / "0", task, count=2, seed=5)

    assert [spec.instance_id for spec in specs] == [8, 9]
    assert (task / "0" / "scene.usda").read_text(encoding="utf-8") == BASE_SCENE
    assert (task / "7").is_dir()
    assert (task / "8" / "scene.usda").is_file()
    manifest = json.loads((task / "scenario_manifest.json").read_text())
    assert manifest["generated_instance_ids"] == [8, 9]
    assert manifest["existing_instance_ids_before_run"] == [0, 7]


def test_profile_rejects_unknown_ids(tmp_path):
    source = _write_source(tmp_path)
    profile = AugmentationProfile.from_dict(
        {"object_pose": {"object_ids": ["missing_object"]}}
    )

    with pytest.raises(ValueError, match="missing_object.*--list-objects"):
        build_generic_scenario_specs(load_scene_info(source), 1, 1, profile)


def test_task_neutral_cli_requires_task():
    with pytest.raises(SystemExit) as error:
        CLI.parse_args([])

    assert error.value.code == 2


def test_task_neutral_cli_generates_in_place_and_keeps_task_name(tmp_path):
    source = _write_source(tmp_path)

    result = CLI.main(
        [
            "--task",
            str(source.parent),
            "--source-instance",
            source.name,
            "--count",
            "2",
            "--seed",
            "42",
            "--skip-preview",
        ]
    )

    assert result == 0
    assert source.parent.name == "arbitrary_task"
    assert (source.parent / "8" / "scene.usda").is_file()
    assert (source.parent / "9" / "scene.usda").is_file()
    manifest = json.loads((source.parent / "scenario_manifest.json").read_text())
    assert manifest["root_seed"] == 42
    assert manifest["scenario_count"] == 2


def test_cli_previews_only_new_ids_and_builds_contact_sheet(monkeypatch, tmp_path):
    from PIL import Image

    source = _write_source(tmp_path)
    config = tmp_path / "task.yaml"
    config.write_text("benchmark: {}\n", encoding="utf-8")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    captured = {}

    monkeypatch.setattr(CLI, "_resolve_preview_config", lambda args, task: config)
    monkeypatch.setattr(CLI, "discover_repo_root", lambda start: repo_root)

    def fake_run_one_config(*args, **kwargs):
        captured["instance_ids"] = kwargs["instance_ids"]
        preview_dir = kwargs["output_dir"] / "task"
        for instance_id in kwargs["instance_ids"]:
            instance_dir = preview_dir / str(instance_id)
            instance_dir.mkdir(parents=True)
            for camera in ("head", "left_hand", "right_hand"):
                Image.new("RGB", (20, 10), "navy").save(instance_dir / f"{camera}.png")
        return {"status": "ok", "task_dir": str(preview_dir)}

    monkeypatch.setattr(CLI, "run_one_config", fake_run_one_config)

    result = CLI.main(
        ["--task", str(source.parent), "--source-instance", "7", "--count", "2"]
    )

    assert result == 0
    assert captured["instance_ids"] == [8, 9]
    assert (
        source.parent
        / "previews"
        / "generated_8_9"
        / "task"
        / "contact_sheet.png"
    ).is_file()
