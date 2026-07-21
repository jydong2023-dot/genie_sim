import ast
import argparse
import importlib.util
import json
import sys
import threading
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

    monkeypatch.syspath_prepend(str(SCRIPT_PATH.parents[1]))
    spec = importlib.util.spec_from_file_location("preview_layout_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_layout_fixture_restores_module_root_in_sys_path():
    module_root = str(SCRIPT_PATH.parents[1])
    original_sys_path = sys.path.copy()
    sys.path[:] = [entry for entry in sys.path if entry != module_root]
    module_patch = pytest.MonkeyPatch()

    try:
        preview_layout.__wrapped__(module_patch)
        module_patch.undo()
        assert module_root not in sys.path
    finally:
        module_patch.undo()
        sys.path[:] = original_sys_path


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

        def generate(self, output_file):
            calls.append((self.task_info, Path(output_file).name))
            Path(output_file).write_text("{}", encoding="utf-8")
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator

    task_info, save_path, files = preview_layout.generate_layouts(template_path, output_dir, None)

    assert task_info == template
    assert save_path == output_dir / "demo"
    assert calls == [
        (template, "demo_0.json"),
        (template, "demo_1.json"),
        (template, "demo_2.json"),
    ]
    assert [path.name for path in files] == [
        "demo_0.json",
        "demo_1.json",
        "demo_2.json",
    ]


@pytest.mark.parametrize(
    "task_name",
    ["", ".", "..", "../escape", "nested/task", r"nested\task"],
)
def test_generate_layouts_rejects_unsafe_task_names_before_constructing_generator(
    preview_layout, tmp_path, task_name
):
    template_path = tmp_path / "template.json"
    write_template(template_path, task=task_name)
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    preview_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(preview_layout.PreviewError, match="task"):
        preview_layout.generate_layouts(template_path, tmp_path / "output", None)

    assert constructed == []


def test_generate_layouts_rejects_absolute_task_before_constructing_generator(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, task=str(tmp_path / "absolute"))
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    preview_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(preview_layout.PreviewError, match="task"):
        preview_layout.generate_layouts(template_path, tmp_path / "output", None)

    assert constructed == []


def test_generate_layouts_rejects_resolved_destination_outside_output_dir(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output_dir / "demo").symlink_to(outside, target_is_directory=True)
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    preview_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(preview_layout.PreviewError, match="output"):
        preview_layout.generate_layouts(template_path, output_dir, None)

    assert constructed == []


def test_generate_layouts_rejects_symlink_output_root_before_constructing_generator(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    real_output = tmp_path / "real-output"
    real_output.mkdir()
    output_link = tmp_path / "output-link"
    output_link.symlink_to(real_output, target_is_directory=True)
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    preview_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(preview_layout.PreviewError, match="symlink"):
        preview_layout.generate_layouts(template_path, output_link, None)

    assert constructed == []
    assert list(real_output.iterdir()) == []


def test_generate_layouts_rechecks_target_containment_before_commit(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=1)
    output_dir = tmp_path / "output"
    outside = tmp_path / "outside"
    outside.mkdir()

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            Path(output_file).write_text("generated", encoding="utf-8")
            (output_dir / "demo").symlink_to(outside, target_is_directory=True)
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(preview_layout.PreviewError, match="output"):
        preview_layout.generate_layouts(template_path, output_dir, None)

    assert list(outside.iterdir()) == []
    assert not (output_dir / ".demo.preview.lock").exists()
    assert sorted(path.name for path in output_dir.iterdir()) == ["demo"]


def test_generate_layouts_refuses_nonempty_destination_without_overwrite(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    save_path = tmp_path / "output" / "demo"
    save_path.mkdir(parents=True)
    marker = save_path / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    preview_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(preview_layout.PreviewError) as exc_info:
        preview_layout.generate_layouts(template_path, tmp_path / "output", None)

    assert "--skip-generate" in str(exc_info.value)
    assert "--overwrite" in str(exc_info.value)
    assert marker.read_text(encoding="utf-8") == "keep"
    assert constructed == []


def test_generate_layouts_allows_empty_destination_without_overwrite(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    save_path = tmp_path / "output" / "demo"
    save_path.mkdir(parents=True)
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

        def generate(self, output_file):
            Path(output_file).write_text("{}", encoding="utf-8")
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator

    _, _, files = preview_layout.generate_layouts(
        template_path, tmp_path / "output", None
    )

    assert len(constructed) == 1
    assert files == [
        save_path / "demo_0.json",
        save_path / "demo_1.json",
        save_path / "demo_2.json",
    ]


def test_generate_layouts_overwrite_allows_generator_to_replace_nonempty_destination(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    save_path = tmp_path / "output" / "demo"
    save_path.mkdir(parents=True)
    old_layouts = [save_path / "demo_0.json", save_path / "demo_9.json"]
    for path in old_layouts:
        path.write_text("old", encoding="utf-8")
    marker = save_path / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    nonmatching = save_path / "demo_server.json"
    nonmatching.write_text("server", encoding="utf-8")
    preview_dir = save_path / "preview"
    preview_dir.mkdir()
    preview_marker = preview_dir / "image.png"
    preview_marker.write_text("image", encoding="utf-8")

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            Path(output_file).write_text("new", encoding="utf-8")
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator

    _, _, files = preview_layout.generate_layouts(
        template_path, tmp_path / "output", None, overwrite=True
    )

    assert files == [
        save_path / "demo_0.json",
        save_path / "demo_1.json",
        save_path / "demo_2.json",
    ]
    assert all(path.read_text(encoding="utf-8") == "new" for path in files)
    assert not old_layouts[1].exists()
    assert marker.read_text(encoding="utf-8") == "keep"
    assert nonmatching.read_text(encoding="utf-8") == "server"
    assert preview_marker.read_text(encoding="utf-8") == "image"


def test_generate_layouts_passes_deep_copy_to_mutating_generator(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    expected = write_template(template_path)
    generator_inputs = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            generator_inputs.append(task_info)
            task_info["task"] = "mutated"
            task_info["recording_setting"]["num_of_episode"] = 99

        def generate(self, output_file):
            Path(output_file).write_text("{}", encoding="utf-8")
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator

    template, _, _ = preview_layout.generate_layouts(
        template_path, tmp_path / "output", None
    )

    assert template == expected
    assert generator_inputs[0] == {
        "task": "mutated",
        "recording_setting": {"num_of_episode": 99},
    }
    assert generator_inputs[0] is not template
    assert generator_inputs[0]["recording_setting"] is not template["recording_setting"]


def test_generate_layouts_explicit_episode_count_overrides_template(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=9)
    generated_counts = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            generated_counts.append(Path(output_file).name)
            Path(output_file).write_text("{}", encoding="utf-8")
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator

    preview_layout.generate_layouts(template_path, tmp_path / "output", 2)

    assert generated_counts == ["demo_0.json", "demo_1.json"]


@pytest.mark.parametrize("overwrite", [False, True])
def test_generate_layouts_existing_lock_fails_before_constructing_generator(
    preview_layout, tmp_path, overwrite
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    lock_path = output_dir / ".demo.preview.lock"
    lock_path.mkdir()
    marker = output_dir / "marker.txt"
    marker.write_text("keep", encoding="utf-8")
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    preview_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(
        preview_layout.PreviewError, match="generation already in progress"
    ):
        preview_layout.generate_layouts(
            template_path, output_dir, 1, overwrite=overwrite
        )

    assert constructed == []
    assert marker.read_text(encoding="utf-8") == "keep"
    assert lock_path.is_dir()


@pytest.mark.parametrize("second_overwrite", [False, True])
def test_generate_layouts_lock_allows_only_one_concurrent_generator(
    preview_layout, tmp_path, second_overwrite
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=1)
    output_dir = tmp_path / "output"
    first_generate_started = threading.Event()
    allow_first_to_finish = threading.Event()
    constructed = []
    generated = []
    first_errors = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

        def generate(self, output_file):
            generated.append(Path(output_file).name)
            first_generate_started.set()
            assert allow_first_to_finish.wait(timeout=2)
            Path(output_file).write_text("owner", encoding="utf-8")
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator

    def run_first():
        try:
            preview_layout.generate_layouts(template_path, output_dir, None)
        except Exception as exc:  # pragma: no cover - asserted below
            first_errors.append(exc)

    owner = threading.Thread(target=run_first)
    owner.start()
    assert first_generate_started.wait(timeout=2)

    with pytest.raises(
        preview_layout.PreviewError, match="generation already in progress"
    ):
        preview_layout.generate_layouts(
            template_path, output_dir, None, overwrite=second_overwrite
        )

    assert len(constructed) == 1
    assert generated == ["demo_0.json"]
    allow_first_to_finish.set()
    owner.join(timeout=2)
    assert not owner.is_alive()
    assert first_errors == []
    assert (output_dir / "demo" / "demo_0.json").read_text(
        encoding="utf-8"
    ) == "owner"


def test_generate_layouts_retries_each_episode_until_success(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=1)
    attempts = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            attempts.append(Path(output_file).name)
            if len(attempts) < 3:
                return False
            Path(output_file).write_text("{}", encoding="utf-8")
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator

    _, _, files = preview_layout.generate_layouts(
        template_path, tmp_path / "output", None
    )

    assert attempts == ["demo_0.json"] * 3
    assert [path.name for path in files] == ["demo_0.json"]


def test_generate_layouts_failed_episode_preserves_existing_layouts_and_cleans_up(
    preview_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=2)
    output_dir = tmp_path / "output"
    save_path = output_dir / "demo"
    save_path.mkdir(parents=True)
    old_layouts = [save_path / "demo_0.json", save_path / "demo_1.json"]
    for path in old_layouts:
        path.write_text(f"old-{path.stem}", encoding="utf-8")
    marker = save_path / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    attempts = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            attempts.append(Path(output_file).name)
            if Path(output_file).name == "demo_0.json":
                Path(output_file).write_text("new", encoding="utf-8")
                return True
            return False

    preview_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(preview_layout.PreviewError, match="5 attempts"):
        preview_layout.generate_layouts(
            template_path, output_dir, None, overwrite=True
        )

    assert attempts == ["demo_0.json"] + ["demo_1.json"] * 5
    assert [path.read_text(encoding="utf-8") for path in old_layouts] == [
        "old-demo_0",
        "old-demo_1",
    ]
    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (output_dir / ".demo.preview.lock").exists()
    assert sorted(path.name for path in output_dir.iterdir()) == ["demo"]


def test_generate_layouts_commit_failure_restores_all_previous_layouts(
    preview_layout, monkeypatch, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=2)
    output_dir = tmp_path / "output"
    save_path = output_dir / "demo"
    save_path.mkdir(parents=True)
    old_contents = {
        save_path / "demo_0.json": "old-zero",
        save_path / "demo_1.json": "old-one",
        save_path / "demo_9.json": "old-nine",
    }
    for path, content in old_contents.items():
        path.write_text(content, encoding="utf-8")
    marker = save_path / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            Path(output_file).write_text(f"new-{Path(output_file).stem}", encoding="utf-8")
            return True

    preview_layout.TaskGenerator = FakeTaskGenerator
    real_replace = preview_layout.os.replace
    failed = False

    def fail_second_install(src, dst):
        nonlocal failed
        src_path = Path(src)
        dst_path = Path(dst)
        if (
            not failed
            and src_path.name == "demo_1.json"
            and dst_path == save_path / "demo_1.json"
            and ".demo.preview-" in src_path.parent.name
        ):
            failed = True
            raise OSError("injected commit failure")
        real_replace(src, dst)

    monkeypatch.setattr(preview_layout.os, "replace", fail_second_install)

    with pytest.raises(OSError, match="injected commit failure"):
        preview_layout.generate_layouts(
            template_path, output_dir, None, overwrite=True
        )

    assert failed is True
    assert {
        path: path.read_text(encoding="utf-8") for path in old_contents
    } == old_contents
    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (output_dir / ".demo.preview.lock").exists()
    assert sorted(path.name for path in output_dir.iterdir()) == ["demo"]


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
    for name in (
        "demo_10.json",
        "demo_2.json",
        "demo_1.json",
        "demo_0.json",
        "demo_server.json",
        "demo_server_server.json",
        "demo_3.json.backup",
        "other_4.json",
    ):
        (save_path / name).write_text("{}", encoding="utf-8")

    task_info, discovered_path, files = preview_layout.discover_layouts(
        template_path, tmp_path / "output"
    )

    assert task_info == template
    assert discovered_path == save_path
    assert [path.name for path in files] == [
        "demo_0.json",
        "demo_1.json",
        "demo_2.json",
        "demo_10.json",
    ]


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


@pytest.mark.parametrize(
    ("client_host", "expected"),
    [
        ("localhost:50051", ("localhost", 50051)),
        ("127.0.0.1:50051", ("127.0.0.1", 50051)),
        ("[::1]:50051", ("::1", 50051)),
    ],
)
def test_parse_grpc_endpoint_accepts_host_and_port(
    preview_layout, client_host, expected
):
    assert preview_layout.parse_grpc_endpoint(client_host) == expected


@pytest.mark.parametrize(
    "client_host",
    [
        "localhost",
        "localhost:not-a-port",
        ":50051",
        "user@localhost:50051",
        "user:password@localhost:50051",
        "localhost:50051/path",
        "localhost:50051?query=yes",
        "localhost:50051#fragment",
        "localhost:50051?",
        "localhost:50051#",
        "[::1]:50051?",
        "[::1]:50051#",
        "local host:50051",
        " localhost:50051",
    ],
)
def test_parse_grpc_endpoint_rejects_invalid_endpoints(preview_layout, client_host):
    with pytest.raises(ValueError, match="expected HOST:PORT"):
        preview_layout.parse_grpc_endpoint(client_host)


def test_require_server_connects_with_timeout_and_closes_socket(
    preview_layout, monkeypatch
):
    calls = []

    class FakeConnection:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.closed = True

    connection = FakeConnection()

    def fake_create_connection(endpoint, timeout):
        calls.append((endpoint, timeout))
        return connection

    monkeypatch.setattr(
        preview_layout.socket, "create_connection", fake_create_connection
    )

    preview_layout.require_server("[::1]:50051", 2.5)

    assert calls == [(('::1', 50051), 2.5)]
    assert connection.closed is True


def test_require_server_reports_how_to_start_server(preview_layout, monkeypatch):
    def refuse_connection(endpoint, timeout):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(
        preview_layout.socket, "create_connection", refuse_connection
    )

    with pytest.raises(preview_layout.PreviewError) as exc_info:
        preview_layout.require_server("localhost:50051", 5.0)

    message = str(exc_info.value)
    assert "localhost:50051" in message
    assert "python scripts/data_collector_server.py --enable_physics" in message


def test_require_server_converts_invalid_endpoint_to_preview_error(preview_layout):
    with pytest.raises(preview_layout.PreviewError, match="expected HOST:PORT"):
        preview_layout.require_server("localhost", 5.0)


def test_positive_float_accepts_positive_value(preview_layout):
    assert preview_layout.positive_float("0.25") == 0.25


@pytest.mark.parametrize("value", ["0", "-0.1", "nan", "inf", "-inf"])
def test_positive_float_rejects_non_positive_values(preview_layout, value):
    with pytest.raises(argparse.ArgumentTypeError):
        preview_layout.positive_float(value)


def test_parse_args_defaults_connect_timeout_to_five_seconds(
    preview_layout, monkeypatch
):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH)])

    args = preview_layout.parse_args()

    assert args.connect_timeout == 5.0


def test_parse_args_uses_positive_float_for_connect_timeout(
    preview_layout, monkeypatch
):
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT_PATH), "--connect-timeout", "1.25"]
    )
    assert preview_layout.parse_args().connect_timeout == 1.25

    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT_PATH), "--connect-timeout", "0"]
    )
    with pytest.raises(SystemExit):
        preview_layout.parse_args()


def test_parse_args_supports_overwrite(preview_layout, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--overwrite"])

    args = preview_layout.parse_args()

    assert args.overwrite is True


def test_parse_args_rejects_overwrite_with_skip_generate(preview_layout, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT_PATH), "--overwrite", "--skip-generate"],
    )

    with pytest.raises(SystemExit):
        preview_layout.parse_args()


def test_prepare_instance_file_writes_rewrite_only_in_temporary_directory(
    preview_layout, tmp_path
):
    src = tmp_path / "demo_0.json"
    src.write_text(json.dumps({"objects": []}), encoding="utf-8")
    temporary_dir = tmp_path / "temporary"
    temporary_dir.mkdir()

    derived = preview_layout.prepare_instance_file(
        src, tmp_path / "assets", True, temporary_dir
    )

    assert derived == temporary_dir / "demo_0_server.json"
    assert derived.is_file()
    assert not src.with_name("demo_0_server.json").exists()


def test_prepare_instance_file_without_rewrite_returns_source_and_creates_nothing(
    preview_layout, tmp_path
):
    src = tmp_path / "demo_0.json"
    src.write_text(json.dumps({"objects": []}), encoding="utf-8")
    temporary_dir = tmp_path / "temporary"

    result = preview_layout.prepare_instance_file(
        src, tmp_path / "assets", False, temporary_dir
    )

    assert result == src
    assert not temporary_dir.exists()


def install_preview_fakes(
    preview_layout,
    monkeypatch,
    tmp_path,
    *,
    generate_error_at=None,
    agent_init_error=None,
    channel_close_error=None,
):
    files = [tmp_path / "demo_0.json", tmp_path / "demo_1.json"]
    for path in files:
        path.write_text("{}", encoding="utf-8")

    agent_events = []
    build_calls = []
    prepare_calls = []
    temporary_dirs = []
    sleep_calls = []

    class FakeChannel:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1
            if channel_close_error is not None:
                raise channel_close_error

    class FakeClient:
        def __init__(self):
            self.channel = FakeChannel()

        @property
        def exit(self):
            raise AssertionError("preview must not access the server exit RPC")

    class FakeRobot:
        def __init__(self):
            self.client = FakeClient()
            self.open_gripper_calls = []

        def open_gripper(self, *, id, detach):
            self.open_gripper_calls.append((id, detach))

    class FakeAgent:
        instances = []

        def __init__(self, robot):
            self.robot = robot
            self.generate_count = 0
            self.instances.append(self)
            agent_events.append(("construct", robot))
            if agent_init_error is not None:
                raise agent_init_error

        def reset(self):
            agent_events.append(("reset",))

        def generate_layout(self, path):
            self.generate_count += 1
            agent_events.append(("generate_layout", path))
            if self.generate_count == generate_error_at:
                raise generation_error

        def __getattr__(self, name):
            forbidden = {
                "run",
                "start_recording",
                "stop_recording",
                "load_task",
                "execute",
            }
            api_kind = "trajectory/planner" if (
                name in forbidden
                or "planner" in name.lower()
                or "trajectory" in name.lower()
            ) else "unexpected"
            raise AssertionError(f"preview accessed {api_kind} agent API: {name}")

    robot = FakeRobot()
    generation_error = RuntimeError("layout generation failed")

    monkeypatch.setattr(
        preview_layout,
        "_import_isaac_client",
        lambda: (FakeAgent, None, None, None),
    )

    def fake_build_robot(template, client_host):
        build_calls.append((template, client_host))
        return robot

    def fake_prepare_instance_file(path, assets_root, rewrite_assets, temporary_dir):
        temporary_dir = Path(temporary_dir)
        temporary_dirs.append(temporary_dir)
        prepare_calls.append((path, assets_root, rewrite_assets, temporary_dir))
        if not rewrite_assets:
            return path
        derived = temporary_dir / f"{path.stem}_server.json"
        derived.write_text("{}", encoding="utf-8")
        return derived

    monkeypatch.setattr(preview_layout, "build_robot", fake_build_robot)
    monkeypatch.setattr(
        preview_layout, "prepare_instance_file", fake_prepare_instance_file
    )
    monkeypatch.setattr(preview_layout.time, "sleep", sleep_calls.append)

    return types.SimpleNamespace(
        files=files,
        robot=robot,
        FakeAgent=FakeAgent,
        generation_error=generation_error,
        agent_events=agent_events,
        build_calls=build_calls,
        prepare_calls=prepare_calls,
        temporary_dirs=temporary_dirs,
        sleep_calls=sleep_calls,
    )


def preview_kwargs(tmp_path, files, *, gui, save_images):
    return {
        "template": {"task": "demo"},
        "files": files,
        "client_host": "localhost:50051",
        "gui": gui,
        "save_images": save_images,
        "cameras": [("head", "/World/head_Camera")],
        "preview_dir": tmp_path / "preview",
        "assets_root": tmp_path / "assets",
        "rewrite_assets": False,
    }


def test_preview_instances_gui_loads_layouts_without_collecting_trajectories(
    preview_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(preview_layout, monkeypatch, tmp_path)
    monkeypatch.setattr(
        "builtins.input", lambda: fakes.agent_events.append(("input",))
    )

    def unexpected_camera_call(*args, **kwargs):
        pytest.fail("save_images=False must not access camera RPCs")

    monkeypatch.setattr(preview_layout, "capture_cameras", unexpected_camera_call)
    monkeypatch.setattr(preview_layout, "save_preview_images", unexpected_camera_call)

    preview_layout.preview_instances(
        **preview_kwargs(tmp_path, fakes.files, gui=True, save_images=False)
    )

    assert fakes.build_calls == [({"task": "demo"}, "localhost:50051")]
    assert len(fakes.FakeAgent.instances) == 1
    assert fakes.agent_events == [
        ("construct", fakes.robot),
        ("reset",),
        ("generate_layout", str(fakes.files[0])),
        ("input",),
        ("reset",),
        ("generate_layout", str(fakes.files[1])),
        ("input",),
    ]
    assert fakes.prepare_calls == [
        (path, tmp_path / "assets", False, fakes.temporary_dirs[0])
        for path in fakes.files
    ]
    assert len(set(fakes.temporary_dirs)) == 1
    assert not fakes.temporary_dirs[0].exists()
    assert fakes.robot.client.channel.close_calls == 1


def test_preview_instances_without_gui_saves_each_layout_without_waiting_for_input(
    preview_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(preview_layout, monkeypatch, tmp_path)

    def unexpected_input():
        pytest.fail("non-GUI preview must not wait for input")

    saved = []
    monkeypatch.setattr("builtins.input", unexpected_input)
    monkeypatch.setattr(
        preview_layout,
        "save_preview_images",
        lambda robot, cameras, preview_dir, stem: saved.append(
            (robot, cameras, preview_dir, stem)
        ),
    )

    preview_layout.preview_instances(
        **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=True)
    )

    assert [call[3] for call in saved] == ["demo_0", "demo_1"]
    assert all(
        call[:3]
        == (
            fakes.robot,
            [("head", "/World/head_Camera")],
            tmp_path / "preview",
        )
        for call in saved
    )
    assert fakes.agent_events[1:] == [
        ("reset",),
        ("generate_layout", str(fakes.files[0])),
        ("reset",),
        ("generate_layout", str(fakes.files[1])),
    ]
    assert fakes.robot.client.channel.close_calls == 1


def test_preview_instances_closes_channel_once_and_propagates_layout_error(
    preview_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(
        preview_layout, monkeypatch, tmp_path, generate_error_at=2
    )

    with pytest.raises(RuntimeError, match="layout generation failed") as exc_info:
        preview_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert exc_info.value is fakes.generation_error
    assert fakes.agent_events[1:] == [
        ("reset",),
        ("generate_layout", str(fakes.files[0])),
        ("reset",),
        ("generate_layout", str(fakes.files[1])),
    ]
    assert fakes.robot.client.channel.close_calls == 1
    assert len(set(fakes.temporary_dirs)) == 1
    assert not fakes.temporary_dirs[0].exists()


def test_preview_instances_isolates_rewritten_files_and_cleans_them(
    preview_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(preview_layout, monkeypatch, tmp_path)
    kwargs = preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
    kwargs["rewrite_assets"] = True

    preview_layout.preview_instances(**kwargs)

    assert len(set(fakes.temporary_dirs)) == 1
    temporary_dir = fakes.temporary_dirs[0]
    assert not temporary_dir.exists()
    assert not list(tmp_path.glob("*_server.json"))
    generated_paths = [
        Path(event[1])
        for event in fakes.agent_events
        if event[0] == "generate_layout"
    ]
    assert all(path.parent == temporary_dir for path in generated_paths)


def test_preview_instances_closes_channel_once_when_agent_construction_fails(
    preview_layout, monkeypatch, tmp_path
):
    agent_init_error = RuntimeError("agent construction failed")
    fakes = install_preview_fakes(
        preview_layout,
        monkeypatch,
        tmp_path,
        agent_init_error=agent_init_error,
    )

    with pytest.raises(RuntimeError, match="agent construction failed") as exc_info:
        preview_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert exc_info.value is agent_init_error
    assert fakes.build_calls == [({"task": "demo"}, "localhost:50051")]
    assert fakes.robot.client.channel.close_calls == 1


def test_preview_instances_ignores_channel_close_error_after_success(
    preview_layout, monkeypatch, tmp_path
):
    close_error = RuntimeError("channel close failed")
    fakes = install_preview_fakes(
        preview_layout,
        monkeypatch,
        tmp_path,
        channel_close_error=close_error,
    )

    preview_layout.preview_instances(
        **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
    )

    assert fakes.robot.client.channel.close_calls == 1


def test_preview_instances_channel_close_error_does_not_mask_layout_error(
    preview_layout, monkeypatch, tmp_path
):
    close_error = RuntimeError("channel close failed")
    fakes = install_preview_fakes(
        preview_layout,
        monkeypatch,
        tmp_path,
        generate_error_at=2,
        channel_close_error=close_error,
    )

    with pytest.raises(RuntimeError, match="layout generation failed") as exc_info:
        preview_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert exc_info.value is fakes.generation_error
    assert fakes.robot.client.channel.close_calls == 1


def test_preview_instances_allows_client_without_channel(
    preview_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(preview_layout, monkeypatch, tmp_path)
    del fakes.robot.client.channel

    preview_layout.preview_instances(
        **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
    )


def test_preview_instances_has_no_trajectory_collection_calls():
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    preview_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "preview_instances"
    )
    called_attributes = {
        node.func.attr
        for node in ast.walk(preview_function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert called_attributes.isdisjoint(
        {
            "run",
            "start_recording",
            "stop_recording",
            "load_task",
            "execute",
            "set_trajectory_list",
            "move",
            "move_pose",
            "moveto",
            "set_joint_positions",
            "exit",
        }
    )


def make_main_args(tmp_path, *, layout_only):
    return types.SimpleNamespace(
        task_template=tmp_path / "template.json",
        output_dir=tmp_path / "output",
        num_episodes=None,
        skip_generate=True,
        overwrite=False,
        layout_only=layout_only,
        gui=False,
        headless=False,
        save_images=False,
        cameras="head",
        client_host="localhost:50051",
        connect_timeout=1.5,
        instance_ids="",
        keep_absolute_assets=False,
    )


def configure_main_dependencies(preview_layout, monkeypatch, tmp_path, args):
    save_path = tmp_path / "output" / "demo"
    layout_path = save_path / "demo_0.json"
    monkeypatch.setattr(preview_layout, "parse_args", lambda: args)
    monkeypatch.setattr(preview_layout, "ensure_sim_assets", lambda: tmp_path)
    monkeypatch.setattr(
        preview_layout,
        "discover_layouts",
        lambda template_path, output_dir: ({}, save_path, [layout_path]),
    )
    return save_path


def test_main_requires_server_before_importing_or_building_robot(
    preview_layout, monkeypatch, tmp_path
):
    args = make_main_args(tmp_path, layout_only=False)
    configure_main_dependencies(preview_layout, monkeypatch, tmp_path, args)
    calls = []

    monkeypatch.setattr(
        preview_layout,
        "require_server",
        lambda endpoint, timeout: calls.append(("require", endpoint, timeout)),
    )
    monkeypatch.setattr(
        preview_layout,
        "resolve_camera_prims",
        lambda template, cameras: [],
    )
    monkeypatch.setattr(
        preview_layout,
        "_import_isaac_client",
        lambda: calls.append(("import",)),
    )
    monkeypatch.setattr(
        preview_layout,
        "build_robot",
        lambda template, client_host: calls.append(("build",)),
    )

    def fake_preview_instances(*args, **kwargs):
        preview_layout._import_isaac_client()
        preview_layout.build_robot({}, "localhost:50051")

    monkeypatch.setattr(preview_layout, "preview_instances", fake_preview_instances)

    assert preview_layout.main() == 0
    assert calls == [
        ("require", "localhost:50051", 1.5),
        ("import",),
        ("build",),
    ]


def test_main_layout_only_does_not_require_server(
    preview_layout, monkeypatch, tmp_path
):
    args = make_main_args(tmp_path, layout_only=True)
    configure_main_dependencies(preview_layout, monkeypatch, tmp_path, args)

    def unexpected_call(*args, **kwargs):
        pytest.fail("layout-only mode must not preflight the server")

    monkeypatch.setattr(preview_layout, "require_server", unexpected_call)
    monkeypatch.setattr(preview_layout, "_import_isaac_client", unexpected_call)
    monkeypatch.setattr(preview_layout, "build_robot", unexpected_call)

    assert preview_layout.main() == 0


def test_ensure_sim_assets_reports_missing_package_as_preview_error(
    preview_layout, monkeypatch
):
    monkeypatch.delenv("SIM_ASSETS", raising=False)
    monkeypatch.setitem(sys.modules, "geniesim_assets", None)

    with pytest.raises(preview_layout.PreviewError, match="SIM_ASSETS is unset"):
        preview_layout.ensure_sim_assets()


def test_ensure_sim_assets_reports_missing_directory_as_preview_error(
    preview_layout, monkeypatch, tmp_path
):
    missing = tmp_path / "missing-assets"
    monkeypatch.setenv("SIM_ASSETS", str(missing))

    with pytest.raises(preview_layout.PreviewError, match=str(missing)):
        preview_layout.ensure_sim_assets()


def test_main_converts_instance_filter_error_to_preview_error(
    preview_layout, monkeypatch, tmp_path
):
    args = make_main_args(tmp_path, layout_only=True)
    args.instance_ids = "7"
    configure_main_dependencies(preview_layout, monkeypatch, tmp_path, args)

    with pytest.raises(preview_layout.PreviewError, match="No layouts matched"):
        preview_layout.main()


def test_save_preview_images_reports_missing_cv2_as_preview_error(
    preview_layout, monkeypatch, tmp_path
):
    monkeypatch.setitem(sys.modules, "cv2", None)

    with pytest.raises(preview_layout.PreviewError, match="opencv-python"):
        preview_layout.save_preview_images(object(), [], tmp_path, "demo_0")


def test_run_cli_reports_expected_errors_without_traceback(
    preview_layout, monkeypatch, capsys
):
    error = preview_layout.PreviewError("server down")

    def fail():
        raise error

    monkeypatch.setattr(preview_layout, "main", fail)

    with pytest.raises(SystemExit) as exc_info:
        preview_layout.run_cli()

    assert exc_info.value.code == 1
    assert capsys.readouterr().err == f"Error: {error}\n"


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_run_cli_preserves_builtin_errors(
    preview_layout, monkeypatch, capsys, error_type
):
    error = error_type("unexpected")

    def fail():
        raise error

    monkeypatch.setattr(preview_layout, "main", fail)

    with pytest.raises(error_type, match="unexpected") as exc_info:
        preview_layout.run_cli()

    assert exc_info.value is error
    assert capsys.readouterr().err == ""
