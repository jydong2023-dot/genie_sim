from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path


DEFAULT_ISAAC_SIM_ROOT = Path(os.environ.get("ISAACSIM_HOME", "/isaac-sim"))
GENIESIM_NUMPY_LIBS_READY = "GENIESIM_NUMPY_LIBS_READY"


def isaacsim_numpy_library_paths(
    isaac_root: str | os.PathLike[str] = DEFAULT_ISAAC_SIM_ROOT,
) -> list[Path]:
    root = Path(isaac_root)
    search_patterns = (
        "extscache/omni.kit.pip_archive-*/pip_prebundle/numpy.libs",
        "kit/python/lib/python*/site-packages/numpy.libs",
    )

    paths: list[Path] = []
    seen: set[str] = set()
    for pattern in search_patterns:
        for path in sorted(root.glob(pattern)):
            if not path.is_dir():
                continue
            path_str = str(path)
            if path_str in seen:
                continue
            paths.append(path)
            seen.add(path_str)
    return paths


def prepend_library_paths(
    env: Mapping[str, str], paths: Iterable[str | os.PathLike[str]]
) -> dict[str, str]:
    updated = dict(env)
    current_entries = [
        entry for entry in updated.get("LD_LIBRARY_PATH", "").split(os.pathsep) if entry
    ]
    known_entries = set(current_entries)

    new_entries: list[str] = []
    for path in paths:
        path_str = str(path)
        if not path_str or path_str in known_entries or path_str in new_entries:
            continue
        new_entries.append(path_str)

    joined_entries = new_entries + current_entries
    if joined_entries:
        updated["LD_LIBRARY_PATH"] = os.pathsep.join(joined_entries)
    return updated


def prepare_isaacsim_numpy_runtime_env(
    env: Mapping[str, str],
    isaac_root: str | os.PathLike[str] = DEFAULT_ISAAC_SIM_ROOT,
) -> dict[str, str]:
    updated = dict(env)
    if updated.get(GENIESIM_NUMPY_LIBS_READY) == "1":
        return updated

    numpy_library_paths = isaacsim_numpy_library_paths(isaac_root)
    if not numpy_library_paths:
        return updated

    updated = prepend_library_paths(updated, numpy_library_paths)
    updated[GENIESIM_NUMPY_LIBS_READY] = "1"
    return updated


def reexec_with_isaacsim_numpy_libs(
    isaac_root: str | os.PathLike[str] = DEFAULT_ISAAC_SIM_ROOT,
) -> None:
    current_env = os.environ.copy()
    updated_env = prepare_isaacsim_numpy_runtime_env(current_env, isaac_root)
    if updated_env.get("LD_LIBRARY_PATH") != current_env.get("LD_LIBRARY_PATH"):
        os.execvpe(sys.executable, [sys.executable, *sys.argv], updated_env)

    ready = updated_env.get(GENIESIM_NUMPY_LIBS_READY)
    if ready is not None:
        os.environ[GENIESIM_NUMPY_LIBS_READY] = ready
