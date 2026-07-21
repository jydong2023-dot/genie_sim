import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "preview_layout.py"


@pytest.fixture
def preview_layout(monkeypatch):
    class StubTaskGenerator:
        pass

    client = types.ModuleType("client")
    client.__path__ = []
    layout = types.ModuleType("client.layout")
    layout.__path__ = []
    task_generate = types.ModuleType("client.layout.task_generate")
    task_generate.TaskGenerator = StubTaskGenerator

    common = types.ModuleType("common")
    common.__path__ = []
    base_utils = types.ModuleType("common.base_utils")
    base_utils.__path__ = []
    logger_module = types.ModuleType("common.base_utils.logger")
    logger_module.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )

    modules = {
        "client": client,
        "client.layout": layout,
        "client.layout.task_generate": task_generate,
        "common": common,
        "common.base_utils": base_utils,
        "common.base_utils.logger": logger_module,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location("preview_layout_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_template(path: Path, *, task: str = "demo", episodes: int = 3) -> dict:
    template = {
        "task": task,
        "recording_setting": {"num_of_episode": episodes},
    }
    path.write_text(json.dumps(template), encoding="utf-8")
    return template


def test_generate_layouts_uses_template_episode_count_and_sorts_files(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    template = write_template(template_path)
    output_dir = tmp_path / "output"
    calls = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            self.task_info = task_info

        def generate_tasks(self, *, save_path, task_num, task_name):
            calls.append((self.task_info, save_path, task_num, task_name))
            destination = Path(save_path)
            destination.mkdir(parents=True)
            (destination / "demo_1.json").write_text("{}", encoding="utf-8")
            (destination / "demo_0.json").write_text("{}", encoding="utf-8")

    preview_layout.TaskGenerator = FakeTaskGenerator

    task_info, save_path, files = preview_layout.generate_layouts(template_path, output_dir, None)

    assert task_info == template
    assert save_path == output_dir / "demo"
    assert calls == [(template, str(save_path), 3, "demo")]
    assert [path.name for path in files] == ["demo_0.json", "demo_1.json"]


def test_generate_layouts_explicit_episode_count_overrides_template(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=9)
    generated_counts = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate_tasks(self, *, save_path, task_num, task_name):
            generated_counts.append(task_num)
            Path(save_path).mkdir(parents=True)

    preview_layout.TaskGenerator = FakeTaskGenerator

    preview_layout.generate_layouts(template_path, tmp_path / "output", 2)

    assert generated_counts == [2]


def test_discover_layouts_raises_when_no_layouts_exist(preview_layout, tmp_path):
    template_path = tmp_path / "template.json"
    write_template(template_path)

    with pytest.raises(FileNotFoundError, match="No layouts"):
        preview_layout.discover_layouts(template_path, tmp_path / "output")


def test_discover_layouts_sorts_existing_layouts(preview_layout, tmp_path):
    template_path = tmp_path / "template.json"
    template = write_template(template_path)
    save_path = tmp_path / "output" / "demo"
    save_path.mkdir(parents=True)
    for name in ("demo_10.json", "demo_02.json", "demo_01.json"):
        (save_path / name).write_text("{}", encoding="utf-8")

    task_info, discovered_path, files = preview_layout.discover_layouts(
        template_path, tmp_path / "output"
    )

    assert task_info == template
    assert discovered_path == save_path
    assert [path.name for path in files] == ["demo_01.json", "demo_02.json", "demo_10.json"]


def test_select_files_matches_comma_separated_numeric_suffixes(preview_layout):
    files = [Path("demo_0.json"), Path("demo_1.json"), Path("demo_12.json")]

    selected = preview_layout.select_files(files, "12, 0")

    assert selected == [Path("demo_0.json"), Path("demo_12.json")]


def test_select_files_raises_when_no_suffix_matches(preview_layout):
    with pytest.raises(ValueError, match="No layouts matched"):
        preview_layout.select_files([Path("demo_0.json")], "7")


def test_rewrite_asset_paths_relative_only_rewrites_internal_string_paths(
    preview_layout, tmp_path
):
    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    internal_dir = assets_root / "objects" / "apple"
    external_path = tmp_path / "external" / "banana.usd"
    task_info = {
        "objects": [
            {
                "data_info_dir": str(internal_dir),
                "obj_path": str(internal_dir / "apple.usd"),
                "model_path": str(assets_root / "models" / "apple.usd"),
                "original_model_path": str(assets_root / "source" / "apple.obj"),
            },
            {
                "data_info_dir": str(external_path),
                "obj_path": 42,
                "model_path": None,
                "untouched": "value",
            },
        ]
    }

    result = preview_layout.rewrite_asset_paths_relative(task_info, assets_root)

    assert result is task_info
    internal_object = task_info["objects"][0]
    assert internal_object["data_info_dir"] == str(Path("objects") / "apple")
    assert internal_object["obj_path"] == str(
        Path("objects") / "apple" / "apple.usd"
    )
    assert internal_object["model_path"] == str(Path("models") / "apple.usd")
    assert internal_object["original_model_path"] == str(Path("source") / "apple.obj")
    external_object = task_info["objects"][1]
    assert external_object["data_info_dir"] == str(external_path)
    assert external_object["obj_path"] == 42
    assert external_object["model_path"] is None
    assert "original_model_path" not in external_object
    assert external_object["untouched"] == "value"
