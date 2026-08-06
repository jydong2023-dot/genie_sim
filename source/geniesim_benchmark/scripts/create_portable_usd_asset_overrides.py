#!/usr/bin/env python3
"""Create a small USD layer that replaces asset-root absolute paths with relative paths."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from pxr import Sdf, Usd


ASSET_TYPES = {Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray}


def _portable_asset_path(
    path: str,
    asset_root: Path,
    output_dir: Path,
    path_remaps: list[tuple[Path, Path]],
) -> str | None:
    asset_path = Path(path)
    if not asset_path.is_absolute():
        return None
    for source_prefix, destination_prefix in path_remaps:
        try:
            suffix = asset_path.relative_to(source_prefix)
        except ValueError:
            continue
        asset_path = destination_prefix / suffix
        break
    try:
        asset_path.relative_to(asset_root)
    except ValueError:
        return None
    return Path(os.path.relpath(asset_path, output_dir)).as_posix()


def _portable_value(
    value,
    type_name,
    asset_root: Path,
    output_dir: Path,
    path_remaps: list[tuple[Path, Path]],
):
    if type_name == Sdf.ValueTypeNames.Asset:
        portable = _portable_asset_path(value.path, asset_root, output_dir, path_remaps)
        return Sdf.AssetPath(portable) if portable else None

    converted = []
    changed = False
    for item in value:
        portable = _portable_asset_path(item.path, asset_root, output_dir, path_remaps)
        converted.append(Sdf.AssetPath(portable) if portable else item)
        changed = changed or portable is not None
    return converted if changed else None


def create_overrides(
    source: Path,
    output: Path,
    asset_root: Path,
    path_remaps: list[tuple[Path, Path]] | None = None,
) -> int:
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    asset_root = asset_root.expanduser().resolve()
    path_remaps = [
        (source_prefix.expanduser().resolve(), destination_prefix.expanduser().resolve())
        for source_prefix, destination_prefix in (path_remaps or [])
    ]
    if not source.is_file():
        raise FileNotFoundError(f"source USD does not exist: {source}")
    if output == source:
        raise ValueError("output must differ from source")

    source_stage = Usd.Stage.Open(str(source))
    if source_stage is None:
        raise RuntimeError(f"failed to open source USD: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}.", suffix=output.suffix, dir=output.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    temporary.unlink()

    try:
        layer = Sdf.Layer.CreateNew(str(temporary))
        override_stage = Usd.Stage.Open(layer)
        count = 0
        for prim in source_stage.TraverseAll():
            for source_attr in prim.GetAttributes():
                type_name = source_attr.GetTypeName()
                value = source_attr.Get()
                if type_name not in ASSET_TYPES or value is None:
                    continue
                portable_value = _portable_value(
                    value, type_name, asset_root, output.parent, path_remaps
                )
                if portable_value is None:
                    continue

                override_prim = override_stage.OverridePrim(prim.GetPath())
                override_attr = override_prim.CreateAttribute(
                    source_attr.GetName(), type_name, custom=source_attr.IsCustom()
                )
                override_attr.Set(portable_value)
                count += 1

        layer.customLayerData = {
            "sourceUsd": source.name,
            "portableAssetOverrideCount": count,
        }
        layer.Save()
        temporary.replace(output)
        return count
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument(
        "--path-remap",
        action="append",
        default=[],
        metavar="SOURCE=DESTINATION",
        help="Remap an obsolete absolute asset-path prefix before making it relative.",
    )
    return parser.parse_args()


def _parse_path_remaps(values: list[str]) -> list[tuple[Path, Path]]:
    remaps = []
    for value in values:
        source, separator, destination = value.partition("=")
        if not separator or not source or not destination:
            raise ValueError(f"invalid --path-remap {value!r}; expected SOURCE=DESTINATION")
        remaps.append((Path(source), Path(destination)))
    return remaps


def main() -> None:
    args = parse_args()
    count = create_overrides(
        args.source,
        args.output,
        args.asset_root,
        _parse_path_remaps(args.path_remap),
    )
    print(f"Wrote {count} portable asset overrides to {args.output.resolve()}")


if __name__ == "__main__":
    main()
