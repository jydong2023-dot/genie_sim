import ast
import argparse
import builtins
import fcntl
import importlib.util
import json
import os
import sys
import threading
import types
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "generate_layout.py"


@pytest.fixture
def generate_layout(monkeypatch):
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
        "common": common,
        "common.base_utils": base_utils,
        "common.base_utils.logger": logger_module,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.syspath_prepend(str(SCRIPT_PATH.parents[1]))
    spec = importlib.util.spec_from_file_location("generate_layout_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_help_loads_when_task_generator_dependencies_are_unavailable(monkeypatch):
    original_import = builtins.__import__

    def reject_task_generator(name, *args, **kwargs):
        if name == "client.layout.task_generate":
            raise ImportError("shapely unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_task_generator)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--help"])

    module = generate_layout.__wrapped__(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        module.parse_args()
    assert exc_info.value.code == 0


def test_generate_layout_fixture_restores_module_root_in_sys_path():
    module_root = str(SCRIPT_PATH.parents[1])
    original_sys_path = sys.path.copy()
    sys.path[:] = [entry for entry in sys.path if entry != module_root]
    module_patch = pytest.MonkeyPatch()

    try:
        generate_layout.__wrapped__(module_patch)
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
    generate_layout, tmp_path
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

    generate_layout.TaskGenerator = FakeTaskGenerator

    task_info, save_path, files = generate_layout.generate_layouts(template_path, output_dir, None)

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
    generate_layout, tmp_path, task_name
):
    template_path = tmp_path / "template.json"
    write_template(template_path, task=task_name)
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="task"):
        generate_layout.generate_layouts(template_path, tmp_path / "output", None)

    assert constructed == []


def test_generate_layouts_rejects_absolute_task_before_constructing_generator(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, task=str(tmp_path / "absolute"))
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="task"):
        generate_layout.generate_layouts(template_path, tmp_path / "output", None)

    assert constructed == []


def test_generate_layouts_rejects_resolved_destination_outside_output_dir(
    generate_layout, tmp_path
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

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="output"):
        generate_layout.generate_layouts(template_path, output_dir, None)

    assert constructed == []


def test_generate_layouts_rejects_symlink_output_root_before_constructing_generator(
    generate_layout, tmp_path
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

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="symlink"):
        generate_layout.generate_layouts(template_path, output_link, None)

    assert constructed == []
    assert list(real_output.iterdir()) == []


@pytest.mark.parametrize("existing_content", [None, "keep"])
def test_generate_layouts_refuses_any_existing_destination_without_constructing_generator(
    generate_layout, tmp_path, existing_content
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    save_path = tmp_path / "output" / "demo"
    save_path.mkdir(parents=True)
    marker = None
    if existing_content is not None:
        marker = save_path / "keep.txt"
        marker.write_text(existing_content, encoding="utf-8")
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError) as exc_info:
        generate_layout.generate_layouts(template_path, tmp_path / "output", None)

    assert "--skip-generate" in str(exc_info.value)
    assert "--output-dir" in str(exc_info.value)
    if marker is not None:
        assert marker.read_text(encoding="utf-8") == existing_content
    assert save_path.is_dir()
    assert constructed == []


def test_generate_layouts_passes_deep_copy_to_mutating_generator(
    generate_layout, tmp_path
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

    generate_layout.TaskGenerator = FakeTaskGenerator

    template, _, _ = generate_layout.generate_layouts(
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
    generate_layout, tmp_path
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

    generate_layout.TaskGenerator = FakeTaskGenerator

    generate_layout.generate_layouts(template_path, tmp_path / "output", 2)

    assert generated_counts == ["demo_0.json", "demo_1.json"]


@pytest.mark.parametrize("episodes", [0, -1, 1.5, True, "2", float("nan")])
def test_generate_layouts_rejects_invalid_template_episode_count_before_generator(
    generate_layout, tmp_path, episodes
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=episodes)
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="positive integer"):
        generate_layout.generate_layouts(template_path, tmp_path / "output", None)

    assert constructed == []
    assert not (tmp_path / "output" / "demo").exists()


@pytest.mark.parametrize("episodes", [0, -1, 1.5, True, float("inf")])
def test_generate_layouts_rejects_invalid_explicit_episode_count_before_generator(
    generate_layout, tmp_path, episodes
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="positive integer"):
        generate_layout.generate_layouts(
            template_path, tmp_path / "output", episodes
        )

    assert constructed == []
    assert not (tmp_path / "output" / "demo").exists()


def test_generate_layouts_held_lock_fails_before_constructing_generator(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    lock_path = output_dir / ".demo.preview.lock"
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    generate_layout.TaskGenerator = FakeTaskGenerator

    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(
            generate_layout.PreviewError, match="generation already in progress"
        ):
            generate_layout.generate_layouts(template_path, output_dir, 1)

    assert constructed == []
    assert lock_path.is_file()


def test_generate_layouts_rejects_symlink_lock_file_before_generator(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside = tmp_path / "outside.lock"
    outside.write_text("outside", encoding="utf-8")
    (output_dir / ".demo.preview.lock").symlink_to(outside)
    constructed = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            constructed.append(task_info)

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="lock"):
        generate_layout.generate_layouts(template_path, output_dir, 1)

    assert constructed == []
    assert outside.read_text(encoding="utf-8") == "outside"


def test_generate_layouts_lock_allows_only_one_concurrent_generator(
    generate_layout, tmp_path
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

    generate_layout.TaskGenerator = FakeTaskGenerator

    def run_first():
        try:
            generate_layout.generate_layouts(template_path, output_dir, None)
        except Exception as exc:  # pragma: no cover - asserted below
            first_errors.append(exc)

    owner = threading.Thread(target=run_first)
    owner.start()
    assert first_generate_started.wait(timeout=2)

    with pytest.raises(
        generate_layout.PreviewError, match="generation already in progress"
    ):
        generate_layout.generate_layouts(template_path, output_dir, None)

    assert len(constructed) == 1
    assert generated == ["demo_0.json"]
    allow_first_to_finish.set()
    owner.join(timeout=2)
    assert not owner.is_alive()
    assert first_errors == []
    assert (output_dir / "demo" / "demo_0.json").read_text(
        encoding="utf-8"
    ) == "owner"


def test_layout_lock_is_released_when_owning_file_descriptor_closes(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=1)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    lock_path = output_dir / ".demo.preview.lock"
    lock_file = lock_path.open("a+")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock_file.close()

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            Path(output_file).write_text("{}", encoding="utf-8")
            return True

    generate_layout.TaskGenerator = FakeTaskGenerator

    _, save_path, files = generate_layout.generate_layouts(
        template_path, output_dir, None
    )

    assert files == [save_path / "demo_0.json"]
    assert lock_path.is_file()


def test_discover_layouts_sees_nothing_until_atomic_publish_completes(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=1)
    output_dir = tmp_path / "output"
    generate_started = threading.Event()
    allow_generate = threading.Event()
    errors = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            generate_started.set()
            assert allow_generate.wait(timeout=2)
            Path(output_file).write_text("{}", encoding="utf-8")
            return True

    generate_layout.TaskGenerator = FakeTaskGenerator

    def run_generate():
        try:
            generate_layout.generate_layouts(template_path, output_dir, None)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    owner = threading.Thread(target=run_generate)
    owner.start()
    assert generate_started.wait(timeout=2)

    with pytest.raises(FileNotFoundError, match="No layouts"):
        generate_layout.discover_layouts(template_path, output_dir)

    allow_generate.set()
    owner.join(timeout=2)
    assert not owner.is_alive()
    assert errors == []
    _, _, files = generate_layout.discover_layouts(template_path, output_dir)
    assert [path.name for path in files] == ["demo_0.json"]


def test_generate_layouts_retries_each_episode_until_success(
    generate_layout, tmp_path
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

    generate_layout.TaskGenerator = FakeTaskGenerator

    _, _, files = generate_layout.generate_layouts(
        template_path, tmp_path / "output", None
    )

    assert attempts == ["demo_0.json"] * 3
    assert [path.name for path in files] == ["demo_0.json"]


def test_generate_layouts_failed_episode_publishes_nothing_and_cleans_staging(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=2)
    output_dir = tmp_path / "output"
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

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="5 attempts"):
        generate_layout.generate_layouts(template_path, output_dir, None)

    assert attempts == ["demo_0.json"] + ["demo_1.json"] * 5
    assert not (output_dir / "demo").exists()
    assert sorted(path.name for path in output_dir.iterdir()) == [
        ".demo.preview.lock"
    ]


def test_generate_layouts_publish_failure_leaves_no_target_or_staging_directory(
    generate_layout, monkeypatch, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=2)
    output_dir = tmp_path / "output"
    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            Path(output_file).write_text(f"new-{Path(output_file).stem}", encoding="utf-8")
            return True

    generate_layout.TaskGenerator = FakeTaskGenerator
    def fail_publish(old_dir_fd, old_name, new_dir_fd, new_name):
        raise generate_layout.PreviewError("injected publish failure")

    monkeypatch.setattr(generate_layout, "_rename_noreplace", fail_publish)

    with pytest.raises(generate_layout.PreviewError, match="injected publish failure"):
        generate_layout.generate_layouts(template_path, output_dir, None)

    assert not (output_dir / "demo").exists()
    assert sorted(path.name for path in output_dir.iterdir()) == [
        ".demo.preview.lock"
    ]


def test_generate_layouts_rejects_recreated_output_root_and_cleans_owned_staging(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=1)
    output_dir = tmp_path / "output"
    moved_root = tmp_path / "moved-output"
    generated_paths = []

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            generated_paths.append(output_file)
            Path(output_file).write_text("generated", encoding="utf-8")
            output_dir.rename(moved_root)
            output_dir.mkdir()
            (output_dir / "external.txt").write_text("external", encoding="utf-8")
            return True

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="identity changed"):
        generate_layout.generate_layouts(template_path, output_dir, None)

    assert generated_paths[0].startswith("/proc/self/fd/")
    assert sorted(path.name for path in moved_root.iterdir()) == [
        ".demo.preview.lock"
    ]
    assert sorted(path.name for path in output_dir.iterdir()) == ["external.txt"]
    assert not (moved_root / "demo").exists()
    assert not (output_dir / "demo").exists()


def test_generate_layouts_rejects_output_root_replaced_by_symlink_and_cleans_staging(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=1)
    output_dir = tmp_path / "output"
    moved_root = tmp_path / "moved-output"
    external = tmp_path / "external"
    external.mkdir()

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            Path(output_file).write_text("generated", encoding="utf-8")
            output_dir.rename(moved_root)
            output_dir.symlink_to(external, target_is_directory=True)
            return True

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="output root"):
        generate_layout.generate_layouts(template_path, output_dir, None)

    assert sorted(path.name for path in moved_root.iterdir()) == [
        ".demo.preview.lock"
    ]
    assert list(external.iterdir()) == []
    assert not (moved_root / "demo").exists()


def test_generate_layouts_never_replaces_target_created_during_generation(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, episodes=1)
    output_dir = tmp_path / "output"

    class FakeTaskGenerator:
        def __init__(self, task_info):
            pass

        def generate(self, output_file):
            Path(output_file).write_text("generated", encoding="utf-8")
            target = output_dir / "demo"
            target.mkdir()
            (target / "external.txt").write_text("external", encoding="utf-8")
            return True

    generate_layout.TaskGenerator = FakeTaskGenerator

    with pytest.raises(generate_layout.PreviewError, match="already exists"):
        generate_layout.generate_layouts(template_path, output_dir, None)

    assert (output_dir / "demo" / "external.txt").read_text(
        encoding="utf-8"
    ) == "external"
    assert sorted(path.name for path in output_dir.iterdir()) == [
        ".demo.preview.lock",
        "demo",
    ]


def test_rename_noreplace_preserves_source_and_existing_target(
    generate_layout, tmp_path
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "new.json").write_text("new", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")

    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(generate_layout.PreviewError, match="already exists"):
            generate_layout._rename_noreplace(
                root_fd, source.name, root_fd, target.name
            )
    finally:
        os.close(root_fd)

    assert (source / "new.json").read_text(encoding="utf-8") == "new"
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_rename_noreplace_passes_real_directory_fds_to_renameat2(
    generate_layout, monkeypatch
):
    calls = []

    class FakeRenameAt2:
        argtypes = None
        restype = None

        def __call__(self, *args):
            calls.append(args)
            return 0

    fake_renameat2 = FakeRenameAt2()
    fake_libc = types.SimpleNamespace(renameat2=fake_renameat2)
    monkeypatch.setattr(
        generate_layout.ctypes, "CDLL", lambda *args, **kwargs: fake_libc
    )

    generate_layout._rename_noreplace(41, "staging", 42, "demo")

    assert calls == [
        (41, b"staging", 42, b"demo", 1),
    ]
    assert all(fd != -100 for fd in (calls[0][0], calls[0][2]))


def test_discover_layouts_raises_when_no_layouts_exist(generate_layout, tmp_path):
    template_path = tmp_path / "template.json"
    write_template(template_path)

    with pytest.raises(FileNotFoundError, match="No layouts"):
        generate_layout.discover_layouts(template_path, tmp_path / "output")


@pytest.mark.parametrize(
    "task_name",
    ["", ".", "..", "../escape", "nested/task", r"nested\task", "/../escaped"],
)
def test_discover_layouts_rejects_unsafe_task_without_creating_lock_or_files(
    generate_layout, tmp_path, task_name
):
    template_path = tmp_path / "template.json"
    write_template(template_path, task=task_name)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with pytest.raises(generate_layout.PreviewError, match="task"):
        generate_layout.discover_layouts(template_path, output_dir)

    assert list(output_dir.iterdir()) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "output",
        "template.json",
    ]


def test_discover_layouts_rejects_absolute_task_without_creating_lock_or_files(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path, task=str(tmp_path / "absolute"))
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with pytest.raises(generate_layout.PreviewError, match="task"):
        generate_layout.discover_layouts(template_path, output_dir)

    assert list(output_dir.iterdir()) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "output",
        "template.json",
    ]


def test_discover_layouts_sorts_existing_layouts(generate_layout, tmp_path):
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

    task_info, discovered_path, files = generate_layout.discover_layouts(
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
    assert not (tmp_path / "output" / ".demo.preview.lock").exists()


def test_discover_layouts_supports_read_only_output_without_creating_lock(
    generate_layout, tmp_path
):
    template_path = tmp_path / "template.json"
    write_template(template_path)
    save_path = tmp_path / "output" / "demo"
    save_path.mkdir(parents=True)
    layout = save_path / "demo_0.json"
    layout.write_text("{}", encoding="utf-8")
    (tmp_path / "output").chmod(0o555)

    try:
        _, _, files = generate_layout.discover_layouts(
            template_path, tmp_path / "output"
        )
    finally:
        (tmp_path / "output").chmod(0o755)

    assert files == [layout]
    assert not (tmp_path / "output" / ".demo.preview.lock").exists()


def test_select_files_matches_comma_separated_numeric_suffixes(generate_layout):
    files = [Path("demo_0.json"), Path("demo_1.json"), Path("demo_12.json")]

    selected = generate_layout.select_files(files, "12, 0")

    assert selected == [Path("demo_0.json"), Path("demo_12.json")]


def test_select_files_raises_when_no_suffix_matches(generate_layout):
    with pytest.raises(ValueError, match="No layouts matched"):
        generate_layout.select_files([Path("demo_0.json")], "7")


def test_rewrite_asset_paths_relative_only_rewrites_internal_string_paths(
    generate_layout, tmp_path
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

    result = generate_layout.rewrite_asset_paths_relative(task_info, assets_root)

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
    generate_layout, client_host, expected
):
    assert generate_layout.parse_grpc_endpoint(client_host) == expected


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
def test_parse_grpc_endpoint_rejects_invalid_endpoints(generate_layout, client_host):
    with pytest.raises(ValueError, match="expected HOST:PORT"):
        generate_layout.parse_grpc_endpoint(client_host)


def test_require_server_waits_for_grpc_readiness_and_closes_channel(
    generate_layout, monkeypatch
):
    calls = []

    class FakeChannel:
        def close(self):
            calls.append(("close",))

    channel = FakeChannel()
    future = types.SimpleNamespace(
        result=lambda timeout: calls.append(("ready", timeout))
    )
    fake_grpc = types.SimpleNamespace(
        FutureTimeoutError=type("FutureTimeoutError", (Exception,), {}),
        RpcError=type("RpcError", (Exception,), {}),
        insecure_channel=lambda endpoint: calls.append(("channel", endpoint)) or channel,
        channel_ready_future=lambda actual_channel: (
            calls.append(("future", actual_channel)) or future
        ),
    )
    monkeypatch.setitem(sys.modules, "grpc", fake_grpc)

    generate_layout.require_server("[::1]:50051", 2.5)

    assert calls == [
        ("channel", "[::1]:50051"),
        ("future", channel),
        ("ready", 2.5),
        ("close",),
    ]


def test_require_server_reports_how_to_start_server(generate_layout, monkeypatch):
    class FutureTimeoutError(Exception):
        pass

    class FakeChannel:
        closed = False

        def close(self):
            self.closed = True

    channel = FakeChannel()
    fake_grpc = types.SimpleNamespace(
        FutureTimeoutError=FutureTimeoutError,
        RpcError=type("RpcError", (Exception,), {}),
        insecure_channel=lambda endpoint: channel,
        channel_ready_future=lambda actual_channel: types.SimpleNamespace(
            result=lambda timeout: (_ for _ in ()).throw(FutureTimeoutError())
        ),
    )
    monkeypatch.setitem(sys.modules, "grpc", fake_grpc)

    with pytest.raises(generate_layout.PreviewError) as exc_info:
        generate_layout.require_server("localhost:50051", 5.0)

    message = str(exc_info.value)
    assert "localhost:50051" in message
    assert "python scripts/data_collector_server.py --enable_physics" in message
    assert channel.closed is True


def test_require_server_converts_invalid_endpoint_to_preview_error(generate_layout):
    with pytest.raises(generate_layout.PreviewError, match="expected HOST:PORT"):
        generate_layout.require_server("localhost", 5.0)


def test_positive_float_accepts_positive_value(generate_layout):
    assert generate_layout.positive_float("0.25") == 0.25


@pytest.mark.parametrize("value", ["0", "-0.1", "nan", "inf", "-inf"])
def test_positive_float_rejects_non_positive_values(generate_layout, value):
    with pytest.raises(argparse.ArgumentTypeError):
        generate_layout.positive_float(value)


def test_positive_int_accepts_positive_integer(generate_layout):
    assert generate_layout.positive_int("3") == 3


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "nan", "inf"])
def test_positive_int_rejects_non_positive_or_non_integer_values(
    generate_layout, value
):
    with pytest.raises(argparse.ArgumentTypeError):
        generate_layout.positive_int(value)


def test_parse_args_defaults_connect_timeout_to_five_seconds(
    generate_layout, monkeypatch
):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH)])

    args = generate_layout.parse_args()

    assert args.connect_timeout == 5.0


def test_parse_args_uses_positive_float_for_connect_timeout(
    generate_layout, monkeypatch
):
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT_PATH), "--connect-timeout", "1.25"]
    )
    assert generate_layout.parse_args().connect_timeout == 1.25

    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT_PATH), "--connect-timeout", "0"]
    )
    with pytest.raises(SystemExit):
        generate_layout.parse_args()


def test_parse_args_rejects_non_positive_num_episodes(generate_layout, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--num-episodes", "0"])
    with pytest.raises(SystemExit):
        generate_layout.parse_args()


def test_prepare_instance_file_writes_rewrite_only_in_temporary_directory(
    generate_layout, tmp_path
):
    src = tmp_path / "demo_0.json"
    src.write_text(json.dumps({"objects": []}), encoding="utf-8")
    temporary_dir = tmp_path / "temporary"
    temporary_dir.mkdir()

    derived = generate_layout.prepare_instance_file(
        src, tmp_path / "assets", True, temporary_dir
    )

    assert derived == temporary_dir / "demo_0_server.json"
    assert derived.is_file()
    assert not src.with_name("demo_0_server.json").exists()


def test_prepare_instance_file_without_rewrite_returns_source_and_creates_nothing(
    generate_layout, tmp_path
):
    src = tmp_path / "demo_0.json"
    src.write_text(json.dumps({"objects": []}), encoding="utf-8")
    temporary_dir = tmp_path / "temporary"

    result = generate_layout.prepare_instance_file(
        src, tmp_path / "assets", False, temporary_dir
    )

    assert result == src
    assert not temporary_dir.exists()


def test_build_robot_passes_connect_timeout_to_isaac_robot(
    generate_layout, monkeypatch
):
    constructed = []

    class FakeTaskGenerator:
        robot_init_pose = {
            "position": [0, 0, 0],
            "quaternion": [1, 0, 0, 0],
        }

        def __init__(self, template):
            pass

    class FakeRobot:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

    class FakeRpcConnectionError(Exception):
        pass

    generate_layout.TaskGenerator = FakeTaskGenerator
    monkeypatch.setattr(
        generate_layout,
        "_import_isaac_client",
        lambda: (None, FakeRobot, None, None, FakeRpcConnectionError),
    )
    template = {
        "robot": {"robot_cfg": "robot.json"},
        "scene": {"scene_usd": "scene.usd"},
    }

    monotonic_values = iter([30.0, 30.25])
    monkeypatch.setattr(generate_layout.time, "monotonic", lambda: next(monotonic_values))

    generate_layout.build_robot(template, "localhost:50051", 0.75)

    assert constructed[0]["connect_timeout"] == 0.5


def install_preview_fakes(
    generate_layout,
    monkeypatch,
    tmp_path,
    *,
    generate_error_at=None,
    agent_init_error=None,
    channel_close_error=None,
):
    monkeypatch.setitem(
        sys.modules,
        "grpc",
        types.SimpleNamespace(
            FutureTimeoutError=type("FutureTimeoutError", (Exception,), {}),
            RpcError=type("RpcError", (Exception,), {}),
        ),
    )
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

        def __getattr__(self, name):
            if name == "open_gripper":
                raise AssertionError("preview must not access open_gripper")
            raise AttributeError(name)

    class FakeRpcConnectionError(ConnectionError):
        pass

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
        generate_layout,
        "_import_isaac_client",
        lambda: (FakeAgent, None, None, None, FakeRpcConnectionError),
    )

    def fake_build_robot(template, client_host, connect_timeout):
        build_calls.append((template, client_host, connect_timeout))
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

    monkeypatch.setattr(generate_layout, "build_robot", fake_build_robot)
    monkeypatch.setattr(
        generate_layout, "prepare_instance_file", fake_prepare_instance_file
    )
    monkeypatch.setattr(generate_layout.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(generate_layout.time, "monotonic", lambda: 100.0)

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
        RpcConnectionError=FakeRpcConnectionError,
    )


def preview_kwargs(tmp_path, files, *, gui, save_images):
    return {
        "template": {"task": "demo"},
        "files": files,
        "client_host": "localhost:50051",
        "connect_timeout": 1.5,
        "gui": gui,
        "save_images": save_images,
        "cameras": [("head", "/World/head_Camera")],
        "preview_dir": tmp_path / "preview",
        "assets_root": tmp_path / "assets",
        "rewrite_assets": False,
    }


def test_preview_instances_gui_loads_layouts_without_collecting_trajectories(
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)
    monkeypatch.setattr(
        "builtins.input", lambda: fakes.agent_events.append(("input",))
    )

    def unexpected_camera_call(*args, **kwargs):
        pytest.fail("save_images=False must not access camera RPCs")

    monkeypatch.setattr(generate_layout, "capture_cameras", unexpected_camera_call)
    monkeypatch.setattr(generate_layout, "save_preview_images", unexpected_camera_call)

    generate_layout.preview_instances(
        **preview_kwargs(tmp_path, fakes.files, gui=True, save_images=False)
    )

    assert fakes.build_calls == [({"task": "demo"}, "localhost:50051", 1.5)]
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
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)

    def unexpected_input():
        pytest.fail("non-GUI preview must not wait for input")

    saved = []
    monkeypatch.setattr("builtins.input", unexpected_input)
    def fake_save(robot, cameras, preview_dir, stem):
        saved.append((robot, cameras, preview_dir, stem))
        return {"head": str(preview_dir / "head.png")}

    monkeypatch.setattr(generate_layout, "save_preview_images", fake_save)

    written_count = generate_layout.preview_instances(
        **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=True)
    )

    assert written_count == 2
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
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(
        generate_layout, monkeypatch, tmp_path, generate_error_at=2
    )

    with pytest.raises(RuntimeError, match="layout generation failed") as exc_info:
        generate_layout.preview_instances(
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
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)
    kwargs = preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
    kwargs["rewrite_assets"] = True

    generate_layout.preview_instances(**kwargs)

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
    generate_layout, monkeypatch, tmp_path
):
    agent_init_error = RuntimeError("agent construction failed")
    fakes = install_preview_fakes(
        generate_layout,
        monkeypatch,
        tmp_path,
        agent_init_error=agent_init_error,
    )

    with pytest.raises(RuntimeError, match="agent construction failed") as exc_info:
        generate_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert exc_info.value is agent_init_error
    assert fakes.build_calls == [({"task": "demo"}, "localhost:50051", 1.5)]
    assert fakes.robot.client.channel.close_calls == 1


def test_preview_instances_converts_grpc_robot_connection_error(
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)

    connection_error = fakes.RpcConnectionError("server raced away")
    monkeypatch.setattr(
        generate_layout,
        "build_robot",
        lambda *args, **kwargs: (_ for _ in ()).throw(connection_error),
    )

    with pytest.raises(generate_layout.PreviewError) as exc_info:
        generate_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert "localhost:50051" in str(exc_info.value)
    assert "python scripts/data_collector_server.py --enable_physics" in str(
        exc_info.value
    )
    assert exc_info.value.__cause__ is connection_error


def test_preview_instances_preserves_ordinary_grpc_robot_error(
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)

    class RpcError(Exception):
        pass

    rpc_error = RpcError("INVALID_ARGUMENT")
    monkeypatch.setattr(
        generate_layout,
        "build_robot",
        lambda *args, **kwargs: (_ for _ in ()).throw(rpc_error),
    )

    with pytest.raises(RpcError, match="INVALID_ARGUMENT") as exc_info:
        generate_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert exc_info.value is rpc_error


def test_preview_instances_deducts_lazy_import_time_from_connection_budget(
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)
    monotonic_values = iter([20.0, 20.4])
    monkeypatch.setattr(generate_layout.time, "monotonic", lambda: next(monotonic_values))

    generate_layout.preview_instances(
        **preview_kwargs(tmp_path, [], gui=False, save_images=False)
    )

    assert fakes.build_calls[0][:2] == ({"task": "demo"}, "localhost:50051")
    assert fakes.build_calls[0][2] == pytest.approx(1.1)


def test_preview_instances_preserves_non_connection_robot_error(
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)
    programming_error = RuntimeError("bad template")
    monkeypatch.setattr(
        generate_layout,
        "build_robot",
        lambda *args, **kwargs: (_ for _ in ()).throw(programming_error),
    )

    with pytest.raises(RuntimeError, match="bad template") as exc_info:
        generate_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert exc_info.value is programming_error


def test_preview_instances_preserves_robot_file_not_found_error(
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)
    file_error = FileNotFoundError("missing robot config")
    monkeypatch.setattr(
        generate_layout,
        "build_robot",
        lambda *args, **kwargs: (_ for _ in ()).throw(file_error),
    )

    with pytest.raises(FileNotFoundError, match="missing robot config") as exc_info:
        generate_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert exc_info.value is file_error


def test_preview_instances_ignores_channel_close_error_after_success(
    generate_layout, monkeypatch, tmp_path
):
    close_error = RuntimeError("channel close failed")
    fakes = install_preview_fakes(
        generate_layout,
        monkeypatch,
        tmp_path,
        channel_close_error=close_error,
    )

    generate_layout.preview_instances(
        **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
    )

    assert fakes.robot.client.channel.close_calls == 1


def test_preview_instances_channel_close_error_does_not_mask_layout_error(
    generate_layout, monkeypatch, tmp_path
):
    close_error = RuntimeError("channel close failed")
    fakes = install_preview_fakes(
        generate_layout,
        monkeypatch,
        tmp_path,
        generate_error_at=2,
        channel_close_error=close_error,
    )

    with pytest.raises(RuntimeError, match="layout generation failed") as exc_info:
        generate_layout.preview_instances(
            **preview_kwargs(tmp_path, fakes.files, gui=False, save_images=False)
        )

    assert exc_info.value is fakes.generation_error
    assert fakes.robot.client.channel.close_calls == 1


def test_preview_instances_allows_client_without_channel(
    generate_layout, monkeypatch, tmp_path
):
    fakes = install_preview_fakes(generate_layout, monkeypatch, tmp_path)
    del fakes.robot.client.channel

    generate_layout.preview_instances(
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
            "open_gripper",
            "exit",
        }
    )


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


def configure_main_dependencies(generate_layout, monkeypatch, tmp_path, args):
    save_path = tmp_path / "output" / "demo"
    layout_path = save_path / "demo_0.json"
    monkeypatch.setattr(generate_layout, "parse_args", lambda: args)
    monkeypatch.setattr(generate_layout, "ensure_sim_assets", lambda: tmp_path)
    monkeypatch.setattr(
        generate_layout,
        "discover_layouts",
        lambda template_path, output_dir: ({}, save_path, [layout_path]),
    )
    return save_path


def test_main_requires_server_before_importing_or_building_robot(
    generate_layout, monkeypatch, tmp_path
):
    args = make_main_args(tmp_path, layout_only=False)
    configure_main_dependencies(generate_layout, monkeypatch, tmp_path, args)
    calls = []
    monotonic_values = iter([10.0, 10.4])
    monkeypatch.setattr(generate_layout.time, "monotonic", lambda: next(monotonic_values))

    monkeypatch.setattr(
        generate_layout,
        "require_server",
        lambda endpoint, timeout: calls.append(("require", endpoint, timeout)),
    )
    monkeypatch.setattr(
        generate_layout,
        "resolve_camera_prims",
        lambda template, cameras: [],
    )
    monkeypatch.setattr(
        generate_layout,
        "_import_isaac_client",
        lambda: calls.append(("import",)),
    )
    monkeypatch.setattr(
        generate_layout,
        "build_robot",
        lambda template, client_host, connect_timeout: calls.append(
            ("build", client_host, connect_timeout)
        ),
    )

    def fake_preview_instances(*args, **kwargs):
        generate_layout._import_isaac_client()
        generate_layout.build_robot(
            {}, kwargs["client_host"], kwargs["connect_timeout"]
        )
        return 0

    monkeypatch.setattr(generate_layout, "preview_instances", fake_preview_instances)

    assert generate_layout.main() == 0
    assert calls[:2] == [
        ("require", "localhost:50051", 1.5),
        ("import",),
    ]
    assert calls[2][:2] == ("build", "localhost:50051")
    assert calls[2][2] == pytest.approx(1.1)


def test_main_does_not_construct_robot_when_preflight_uses_total_budget(
    generate_layout, monkeypatch, tmp_path
):
    args = make_main_args(tmp_path, layout_only=False)
    configure_main_dependencies(generate_layout, monkeypatch, tmp_path, args)
    monotonic_values = iter([10.0, 11.5])
    monkeypatch.setattr(generate_layout.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(generate_layout, "require_server", lambda *args: None)
    monkeypatch.setattr(generate_layout, "resolve_camera_prims", lambda *args: [])
    monkeypatch.setattr(
        generate_layout,
        "preview_instances",
        lambda *args, **kwargs: pytest.fail("expired budget must not build robot"),
    )

    with pytest.raises(generate_layout.PreviewError, match="connection timeout"):
        generate_layout.main()


def test_main_layout_only_does_not_require_server(
    generate_layout, monkeypatch, tmp_path
):
    args = make_main_args(tmp_path, layout_only=True)
    configure_main_dependencies(generate_layout, monkeypatch, tmp_path, args)

    def unexpected_call(*args, **kwargs):
        pytest.fail("layout-only mode must not preflight the server")

    monkeypatch.setattr(generate_layout, "require_server", unexpected_call)
    monkeypatch.setattr(generate_layout, "_import_isaac_client", unexpected_call)
    monkeypatch.setattr(generate_layout, "build_robot", unexpected_call)

    assert generate_layout.main() == 0


def test_ensure_sim_assets_reports_missing_package_as_preview_error(
    generate_layout, monkeypatch
):
    monkeypatch.delenv("SIM_ASSETS", raising=False)
    monkeypatch.setitem(sys.modules, "geniesim_assets", None)

    with pytest.raises(generate_layout.PreviewError, match="SIM_ASSETS is unset"):
        generate_layout.ensure_sim_assets()


def test_ensure_sim_assets_reports_missing_directory_as_preview_error(
    generate_layout, monkeypatch, tmp_path
):
    missing = tmp_path / "missing-assets"
    monkeypatch.setenv("SIM_ASSETS", str(missing))

    with pytest.raises(generate_layout.PreviewError, match=str(missing)):
        generate_layout.ensure_sim_assets()


def test_main_converts_instance_filter_error_to_preview_error(
    generate_layout, monkeypatch, tmp_path
):
    args = make_main_args(tmp_path, layout_only=True)
    args.instance_ids = "7"
    configure_main_dependencies(generate_layout, monkeypatch, tmp_path, args)

    with pytest.raises(generate_layout.PreviewError, match="No layouts matched"):
        generate_layout.main()


def test_save_preview_images_reports_missing_cv2_as_preview_error(
    generate_layout, monkeypatch, tmp_path
):
    monkeypatch.setitem(sys.modules, "cv2", None)

    with pytest.raises(generate_layout.PreviewError, match="opencv-python"):
        generate_layout.save_preview_images(object(), [], tmp_path, "demo_0")


def test_save_preview_images_second_failure_publishes_no_images(
    generate_layout, monkeypatch, tmp_path
):
    images = [object(), object()]
    write_calls = []

    def imwrite(path, image):
        write_calls.append(path)
        if len(write_calls) == 2:
            return False
        Path(path).write_bytes(b"temporary")
        return True

    fake_cv2 = types.SimpleNamespace(
        COLOR_RGB2BGR=1,
        cvtColor=lambda actual, code: actual,
        imwrite=imwrite,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(generate_layout, "capture_cameras", lambda robot, prims: images)

    with pytest.raises(generate_layout.PreviewError, match="Failed to write"):
        generate_layout.save_preview_images(
            object(),
            [("head", "/World/head"), ("left", "/World/left")],
            tmp_path,
            "demo_0",
        )

    assert not (tmp_path / "head.png").exists()
    assert not (tmp_path / "left.png").exists()


def test_save_preview_images_rejects_short_camera_response(
    generate_layout, monkeypatch, tmp_path
):
    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace())
    monkeypatch.setattr(
        generate_layout, "capture_cameras", lambda robot, prims: [object()]
    )

    with pytest.raises(generate_layout.PreviewError, match="left"):
        generate_layout.save_preview_images(
            object(),
            [("head", "/World/head"), ("left", "/World/left")],
            tmp_path,
            "demo_0",
        )

    assert list(tmp_path.glob("*.png")) == []


def test_save_preview_images_rejects_none_camera_image(
    generate_layout, monkeypatch, tmp_path
):
    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace())
    monkeypatch.setattr(
        generate_layout, "capture_cameras", lambda robot, prims: [object(), None]
    )

    with pytest.raises(generate_layout.PreviewError, match="left"):
        generate_layout.save_preview_images(
            object(),
            [("head", "/World/head"), ("left", "/World/left")],
            tmp_path,
            "demo_0",
        )

    assert list(tmp_path.glob("*.png")) == []


def test_save_preview_images_publishes_all_images_after_all_writes_succeed(
    generate_layout, monkeypatch, tmp_path
):
    images = [object(), object()]

    def imwrite(path, image):
        Path(path).write_bytes(b"image")
        return True

    fake_cv2 = types.SimpleNamespace(
        COLOR_RGB2BGR=1,
        cvtColor=lambda actual, code: actual,
        imwrite=imwrite,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(generate_layout, "capture_cameras", lambda robot, prims: images)

    written = generate_layout.save_preview_images(
        object(),
        [("head", "/World/head"), ("left", "/World/left")],
        tmp_path,
        "demo_0",
    )

    assert written == {
        "head": str(tmp_path / "head.png"),
        "left": str(tmp_path / "left.png"),
    }
    assert (tmp_path / "head.png").read_bytes() == b"image"
    assert (tmp_path / "left.png").read_bytes() == b"image"


@pytest.mark.parametrize(("headless", "save_images"), [(True, False), (False, True)])
def test_main_rejects_image_modes_without_resolved_cameras(
    generate_layout, monkeypatch, tmp_path, headless, save_images
):
    args = make_main_args(tmp_path, layout_only=False)
    args.headless = headless
    args.save_images = save_images
    configure_main_dependencies(generate_layout, monkeypatch, tmp_path, args)
    monkeypatch.setattr(generate_layout, "require_server", lambda *args: None)
    monkeypatch.setattr(generate_layout, "resolve_camera_prims", lambda *args: [])
    monkeypatch.setattr(
        generate_layout,
        "preview_instances",
        lambda *args, **kwargs: pytest.fail("preview must not start without cameras"),
    )

    with pytest.raises(generate_layout.PreviewError, match="No cameras resolved"):
        generate_layout.main()


def test_main_only_prints_preview_directory_after_an_image_is_written(
    generate_layout, monkeypatch, tmp_path, capsys
):
    args = make_main_args(tmp_path, layout_only=False)
    args.headless = True
    configure_main_dependencies(generate_layout, monkeypatch, tmp_path, args)
    monkeypatch.setattr(generate_layout, "require_server", lambda *args: None)
    monkeypatch.setattr(
        generate_layout,
        "resolve_camera_prims",
        lambda *args: [("head", "/World/head")],
    )
    monkeypatch.setattr(generate_layout, "preview_instances", lambda *args, **kwargs: 0)

    assert generate_layout.main() == 0
    assert "Preview images:" not in capsys.readouterr().out


def test_run_cli_reports_expected_errors_without_traceback(
    generate_layout, monkeypatch, capsys
):
    error = generate_layout.PreviewError("server down")

    def fail():
        raise error

    monkeypatch.setattr(generate_layout, "main", fail)

    with pytest.raises(SystemExit) as exc_info:
        generate_layout.run_cli()

    assert exc_info.value.code == 1
    assert capsys.readouterr().err == f"Error: {error}\n"


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_run_cli_preserves_builtin_errors(
    generate_layout, monkeypatch, capsys, error_type
):
    error = error_type("unexpected")

    def fail():
        raise error

    monkeypatch.setattr(generate_layout, "main", fail)

    with pytest.raises(error_type, match="unexpected") as exc_info:
        generate_layout.run_cli()

    assert exc_info.value is error
    assert capsys.readouterr().err == ""
