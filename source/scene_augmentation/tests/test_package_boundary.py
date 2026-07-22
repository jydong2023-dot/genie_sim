import json
from pathlib import Path

from PIL import Image

from scene_augmentation import build_contact_sheet, generate_augmented_scenarios
from scene_augmentation.cli import main


BASE_SCENE = '''#usda 1.0
(
    defaultPrim = "World"
)
def "World" {}
'''


def _entry(category, xyz):
    return {
        "description": {
            "object_category": category,
            "semantic_name": category,
        },
        "keywords": category,
        "tags": [],
        "xyz": xyz,
        "xyzw": [0.0, 0.0, 0.0, 1.0],
    }


def _task(tmp_path: Path) -> Path:
    task = tmp_path / "portable_task"
    source = task / "0"
    source.mkdir(parents=True)
    (source / "scene.usda").write_text(BASE_SCENE, encoding="utf-8")
    (source / "scene_info.json").write_text(
        json.dumps(
            {
                "layout": {
                    "table_001": _entry(["furniture", "table"], [0, 0, 0.3]),
                    "object_001": _entry(["object"], [0, 0, 0.8]),
                }
            }
        ),
        encoding="utf-8",
    )
    return task


def test_core_generates_without_benchmark_package(tmp_path):
    task = _task(tmp_path)

    specs = generate_augmented_scenarios(task / "0", task, count=2, seed=3)

    assert [spec.instance_id for spec in specs] == [1, 2]
    assert (task / "1" / "scene.usda").is_file()
    assert (task / "2" / "scenario.json").is_file()


def test_standalone_cli_requires_explicit_task_directory(tmp_path):
    task = _task(tmp_path)

    assert main(["--task-dir", str(task), "--count", "1"]) == 0
    assert (task / "1" / "scene.usda").is_file()


def test_contact_sheet_is_simulator_independent(tmp_path):
    for instance_id in (4, 5):
        instance = tmp_path / str(instance_id)
        instance.mkdir()
        for camera in ("head", "left_hand", "right_hand"):
            Image.new("RGB", (12, 8), "navy").save(instance / f"{camera}.png")

    output = build_contact_sheet(tmp_path, [4, 5])

    assert output == tmp_path / "contact_sheet.png"
    assert output.is_file()
