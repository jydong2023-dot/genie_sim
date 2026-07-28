from pathlib import Path

from common.base_utils.isaac_numpy_runtime import (
    GENIESIM_NUMPY_LIBS_READY,
    isaacsim_numpy_library_paths,
    prepare_isaacsim_numpy_runtime_env,
    prepend_library_paths,
)


def test_finds_isaacsim_numpy_library_paths(tmp_path):
    isaac_root = tmp_path / "isaac-sim"
    pip_archive_libs = (
        isaac_root
        / "extscache"
        / "omni.kit.pip_archive-0.0.0+hash.lx64.cp311"
        / "pip_prebundle"
        / "numpy.libs"
    )
    kit_python_libs = (
        isaac_root
        / "kit"
        / "python"
        / "lib"
        / "python3.11"
        / "site-packages"
        / "numpy.libs"
    )
    scipy_libs = (
        isaac_root
        / "kit"
        / "python"
        / "lib"
        / "python3.11"
        / "site-packages"
        / "scipy.libs"
    )
    for path in (kit_python_libs, pip_archive_libs, scipy_libs):
        path.mkdir(parents=True)

    assert isaacsim_numpy_library_paths(isaac_root) == [
        pip_archive_libs,
        kit_python_libs,
    ]


def test_prepend_library_paths_preserves_existing_entries_without_duplicates(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    old = tmp_path / "old"
    env = {"LD_LIBRARY_PATH": f"{old}:{first}"}

    updated = prepend_library_paths(env, [first, second])

    assert updated is not env
    assert env["LD_LIBRARY_PATH"] == f"{old}:{first}"
    assert updated["LD_LIBRARY_PATH"] == f"{second}:{old}:{first}"


def test_prepare_runtime_env_sets_marker_and_leaves_marked_env_unchanged(tmp_path):
    isaac_root = tmp_path / "isaac-sim"
    libs = (
        isaac_root
        / "extscache"
        / "omni.kit.pip_archive-0.0.0+hash.lx64.cp311"
        / "pip_prebundle"
        / "numpy.libs"
    )
    libs.mkdir(parents=True)
    env = {"LD_LIBRARY_PATH": "/existing"}

    updated = prepare_isaacsim_numpy_runtime_env(env, isaac_root)

    assert updated[GENIESIM_NUMPY_LIBS_READY] == "1"
    assert updated["LD_LIBRARY_PATH"] == f"{libs}:/existing"

    marked = updated.copy()
    marked["LD_LIBRARY_PATH"] = "/already-ready"
    assert prepare_isaacsim_numpy_runtime_env(marked, isaac_root) == marked
