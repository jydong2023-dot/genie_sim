# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Runtime path discovery for generator assets and benchmark outputs."""

import os
from importlib.util import find_spec
from pathlib import Path


ASSETS_DIR_ENV = "GENIESIM_ASSETS_DIR"
OUTPUT_DIR_ENV = "GENIESIM_GENERATOR_OUTPUT_DIR"


def _package_directory(package_name: str) -> Path | None:
    spec = find_spec(package_name)
    if spec is None:
        return None

    locations = spec.submodule_search_locations
    if locations:
        return Path(next(iter(locations))).expanduser().resolve()
    if spec.origin and spec.origin not in {"built-in", "frozen"}:
        return Path(spec.origin).expanduser().resolve().parent
    return None


def _explicit_directory(variable: str) -> Path | None:
    value = os.environ.get(variable)
    if not value:
        return None

    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise RuntimeError(f"{variable} points to a missing directory: {path}")
    return path


def resolve_assets_root() -> Path:
    """Return the directory containing the active ``geniesim_assets`` package."""

    explicit = _explicit_directory(ASSETS_DIR_ENV)
    if explicit is not None:
        if not (explicit / "__init__.py").is_file():
            raise RuntimeError(f"{ASSETS_DIR_ENV} is not a geniesim_assets package: {explicit}")
        return explicit

    package = _package_directory("geniesim_assets")
    if package is None or not (package / "__init__.py").is_file():
        raise RuntimeError(
            "Cannot locate the geniesim_assets package. "
            f"Install it or set {ASSETS_DIR_ENV} to its package directory."
        )
    return package


def resolve_generator_output_root() -> Path:
    """Return the benchmark ``config/llm_task`` output directory."""

    explicit = _explicit_directory(OUTPUT_DIR_ENV)
    if explicit is not None:
        return explicit

    attempted: list[Path] = []
    benchmark_package = _package_directory("geniesim_benchmark")
    if benchmark_package is not None:
        installed_output = benchmark_package / "benchmark" / "config" / "llm_task"
        attempted.append(installed_output)
        if installed_output.is_dir():
            return installed_output.resolve()

    distribution_root = Path(__file__).resolve().parents[2]
    sibling_output = (
        distribution_root.parent
        / "geniesim_benchmark"
        / "src"
        / "geniesim_benchmark"
        / "benchmark"
        / "config"
        / "llm_task"
    )
    attempted.append(sibling_output)
    if sibling_output.is_dir():
        return sibling_output.resolve()

    attempted_text = ", ".join(str(path) for path in attempted)
    raise RuntimeError(
        "Cannot locate the benchmark llm_task output directory. "
        f"Set {OUTPUT_DIR_ENV} to an existing directory. Tried: {attempted_text}"
    )


def resolve_asset_path(asset_url: str | os.PathLike[str]) -> Path:
    """Resolve one asset-index URL and require that its payload exists."""

    asset_path = Path(asset_url).expanduser()
    if not asset_path.is_absolute():
        asset_path = resolve_assets_root() / asset_path
    asset_path = asset_path.resolve()
    if not asset_path.is_file():
        raise FileNotFoundError(f"Asset payload does not exist: {asset_url} -> {asset_path}")
    return asset_path
