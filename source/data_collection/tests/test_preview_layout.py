import argparse
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


def make_main_args(tmp_path, *, layout_only):
    return types.SimpleNamespace(
        task_template=tmp_path / "template.json",
        output_dir=tmp_path / "output",
        num_episodes=None,
        skip_generate=True,
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
