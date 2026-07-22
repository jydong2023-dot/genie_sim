#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Config-driven augmentation of a portable scene bundle."""

from __future__ import annotations

import colorsys
import json
import math
import random
import shutil
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


GENERATOR_VERSION = 2
DEFAULT_DIMENSIONS = (
    "object_pose",
    "lighting",
    "table_height",
    "table_appearance",
    "combined",
)


def _as_pair(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must be a two-element JSON array")
    low, high = float(value[0]), float(value[1])
    if low > high:
        raise ValueError(f"{name} lower bound must not exceed upper bound")
    return low, high


def _float_list(value: Any, name: str) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty JSON array")
    return tuple(float(item) for item in value)


def _string_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} entries must be non-empty strings")
    return tuple(value)


def _color(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} must be an RGB array")
    rgb = tuple(float(component) for component in value)
    if any(component < 0.0 or component > 1.0 for component in rgb):
        raise ValueError(f"{name} components must be in [0, 1]")
    return rgb


@dataclass(frozen=True)
class AugmentationProfile:
    """Validated controls for deterministic scenario sampling."""

    dimensions: tuple[str, ...] = DEFAULT_DIMENSIONS
    include_baseline: bool = True
    movable_object_ids: tuple[str, ...] = ()
    table_ids: tuple[str, ...] = ()
    move_with_table_ids: tuple[str, ...] = ()
    x_range: tuple[float, float] = (-0.20, 0.20)
    y_range: tuple[float, float] = (-0.25, 0.25)
    yaw_range_deg: tuple[float, float] = (-30.0, 30.0)
    min_separation: float = 0.08
    table_height_offsets: tuple[float, ...] = (-0.05, -0.025, 0.025, 0.05)
    light_temperatures: tuple[float, ...] = (3000.0, 5000.0, 7000.0, 9000.0)
    light_intensities: tuple[float, ...] = (500.0, 1000.0, 3000.0, 6000.0)
    table_colors: tuple[tuple[float, float, float], ...] = (
        (0.18, 0.18, 0.18),
        (0.55, 0.32, 0.15),
        (0.75, 0.75, 0.75),
        (0.15, 0.30, 0.55),
    )
    table_roughness: tuple[float, ...] = (0.25, 0.5, 0.8)
    table_metallic: tuple[float, ...] = (0.0,)
    table_textures: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "AugmentationProfile":
        payload = payload or {}
        if not isinstance(payload, dict):
            raise ValueError("augmentation profile must be a JSON object")

        object_pose = payload.get("object_pose", {})
        lighting = payload.get("lighting", {})
        table_height = payload.get("table_height", {})
        appearance = payload.get("table_appearance", {})
        for name, section in (
            ("object_pose", object_pose),
            ("lighting", lighting),
            ("table_height", table_height),
            ("table_appearance", appearance),
        ):
            if not isinstance(section, dict):
                raise ValueError(f"{name} must be a JSON object")

        dimensions = _string_list(
            payload.get("dimensions", list(DEFAULT_DIMENSIONS)), "dimensions"
        )
        unknown = set(dimensions) - set(DEFAULT_DIMENSIONS)
        if unknown:
            raise ValueError(f"unknown augmentation dimensions: {sorted(unknown)}")
        if not dimensions:
            raise ValueError("dimensions must contain at least one augmentation")

        raw_colors = appearance.get("colors", [list(color) for color in cls.table_colors])
        if not isinstance(raw_colors, list) or not raw_colors:
            raise ValueError("table_appearance.colors must be a non-empty JSON array")
        profile = cls(
            dimensions=dimensions,
            include_baseline=bool(payload.get("include_baseline", True)),
            movable_object_ids=_string_list(
                object_pose.get("object_ids", []), "object_pose.object_ids"
            ),
            table_ids=_string_list(
                payload.get("table_ids", appearance.get("table_ids", [])), "table_ids"
            ),
            move_with_table_ids=_string_list(
                table_height.get("move_with_table_ids", []),
                "table_height.move_with_table_ids",
            ),
            x_range=_as_pair(object_pose.get("x_range", [-0.20, 0.20]), "object_pose.x_range"),
            y_range=_as_pair(object_pose.get("y_range", [-0.25, 0.25]), "object_pose.y_range"),
            yaw_range_deg=_as_pair(
                object_pose.get("yaw_range_deg", [-30.0, 30.0]),
                "object_pose.yaw_range_deg",
            ),
            min_separation=float(object_pose.get("min_separation", 0.08)),
            table_height_offsets=_float_list(
                table_height.get("offsets", [-0.05, -0.025, 0.025, 0.05]),
                "table_height.offsets",
            ),
            light_temperatures=_float_list(
                lighting.get("temperatures", [3000, 5000, 7000, 9000]),
                "lighting.temperatures",
            ),
            light_intensities=_float_list(
                lighting.get("intensities", [500, 1000, 3000, 6000]),
                "lighting.intensities",
            ),
            table_colors=tuple(
                _color(item, f"table_appearance.colors[{index}]")
                for index, item in enumerate(raw_colors)
            ),
            table_roughness=_float_list(
                appearance.get("roughness", [0.25, 0.5, 0.8]),
                "table_appearance.roughness",
            ),
            table_metallic=_float_list(
                appearance.get("metallic", [0.0]), "table_appearance.metallic"
            ),
            table_textures=_string_list(
                appearance.get("textures", []), "table_appearance.textures"
            ),
        )
        if profile.min_separation < 0:
            raise ValueError("object_pose.min_separation must be non-negative")
        if any(value < 0 for value in profile.light_intensities):
            raise ValueError("lighting intensities must be non-negative")
        return profile


@dataclass(frozen=True)
class GenericScenarioSpec:
    instance_id: int
    dimension: str
    scenario_seed: int
    object_poses: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    table_height_offset: float = 0.0
    light_config: dict[str, Any] = field(default_factory=dict)
    table_appearance: dict[str, Any] = field(default_factory=dict)


def load_profile(path: Path | None) -> AugmentationProfile:
    if path is None:
        return AugmentationProfile()
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    profile = AugmentationProfile.from_dict(payload)
    if profile.table_textures:
        resolved = []
        for texture in profile.table_textures:
            texture_path = Path(texture).expanduser()
            if not texture_path.is_absolute():
                texture_path = path.parent / texture_path
            if not texture_path.is_file():
                raise FileNotFoundError(f"table texture does not exist: {texture_path}")
            resolved.append(str(texture_path.resolve()))
        profile = AugmentationProfile(
            **{**profile.__dict__, "table_textures": tuple(resolved)}
        )
    return profile


def load_scene_info(source_dir: Path) -> dict[str, Any]:
    path = Path(source_dir) / "scene_info.json"
    if not path.is_file():
        raise FileNotFoundError(f"source scene is missing {path.name}: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("layout"), dict) or not payload["layout"]:
        raise ValueError(f"{path} must contain a non-empty layout object")
    return payload


def _semantic_tokens(entry: dict[str, Any]) -> set[str]:
    description = entry.get("description", {})
    values: list[Any] = [
        entry.get("keywords", []),
        entry.get("tags", []),
        description.get("object_category", []),
        description.get("semantic_name", []),
    ]
    tokens: set[str] = set()
    for value in values:
        if isinstance(value, str):
            tokens.add(value.lower())
        elif isinstance(value, list):
            tokens.update(str(item).lower() for item in value)
    return tokens


def discover_object_ids(
    scene_info: dict[str, Any], profile: AugmentationProfile
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    layout = scene_info["layout"]
    unknown = (set(profile.movable_object_ids) | set(profile.table_ids)) - set(layout)
    if unknown:
        raise ValueError(
            "profile references object IDs absent from scene_info: "
            f"{sorted(unknown)}. Run the generator with --task <task> "
            "--source-instance <id> --list-objects, then update or remove the explicit IDs."
        )

    table_ids = profile.table_ids or tuple(
        object_id
        for object_id, entry in layout.items()
        if "table" in _semantic_tokens(entry) or "table" in object_id.lower()
    )
    movable_ids = profile.movable_object_ids or tuple(
        object_id for object_id in layout if object_id not in table_ids
    )
    follow_ids = profile.move_with_table_ids or movable_ids
    missing_follow = set(follow_ids) - set(layout)
    if missing_follow:
        raise ValueError(
            f"table_height.move_with_table_ids absent from scene_info: {sorted(missing_follow)}"
        )
    if not movable_ids:
        raise ValueError("no movable objects discovered; set object_pose.object_ids explicitly")
    return tuple(movable_ids), tuple(table_ids), tuple(follow_ids)


def _quaternion_from_yaw(yaw_deg: float) -> list[float]:
    half = math.radians(yaw_deg) / 2.0
    return [0.0, 0.0, round(math.sin(half), 6), round(math.cos(half), 6)]


def _sample_object_poses(
    rng: random.Random,
    object_ids: tuple[str, ...],
    layout: dict[str, Any],
    profile: AugmentationProfile,
) -> dict[str, dict[str, list[float]]]:
    for _ in range(1000):
        poses: dict[str, dict[str, list[float]]] = {}
        xy_positions = []
        for object_id in object_ids:
            xyz = layout[object_id].get("xyz")
            if not isinstance(xyz, list) or len(xyz) != 3:
                raise ValueError(f"layout.{object_id}.xyz must contain three numbers")
            x = round(rng.uniform(*profile.x_range), 6)
            y = round(rng.uniform(*profile.y_range), 6)
            yaw = rng.uniform(*profile.yaw_range_deg)
            poses[object_id] = {
                "xyz": [x, y, float(xyz[2])],
                "xyzw": _quaternion_from_yaw(yaw),
            }
            xy_positions.append((x, y))
        if all(
            math.dist(xy_positions[i], xy_positions[j]) >= profile.min_separation
            for i in range(len(xy_positions))
            for j in range(i + 1, len(xy_positions))
        ):
            return poses
    raise RuntimeError(
        "could not sample non-overlapping object poses after 1000 attempts; "
        "widen the XY ranges or reduce min_separation"
    )


def build_generic_scenario_specs(
    scene_info: dict[str, Any],
    count: int,
    seed: int,
    profile: AugmentationProfile,
    start_instance_id: int = 0,
) -> list[GenericScenarioSpec]:
    if count < 1:
        raise ValueError("count must be at least 1")
    movable_ids, table_ids, _ = discover_object_ids(scene_info, profile)
    dimensions = tuple(
        dimension
        for dimension in profile.dimensions
        if table_ids or dimension not in {"table_height", "table_appearance"}
    )
    if not dimensions:
        raise ValueError(
            "no applicable dimensions remain; set table_ids or enable object_pose/lighting"
        )
    rng = random.Random(seed)
    specs = []
    if start_instance_id < 0:
        raise ValueError("start_instance_id must be non-negative")
    for offset in range(count):
        instance_id = start_instance_id + offset
        if offset == 0 and profile.include_baseline:
            dimension = "baseline"
        else:
            index = offset - (1 if profile.include_baseline else 0)
            dimension = dimensions[index % len(dimensions)]
        enabled = set(DEFAULT_DIMENSIONS[:-1]) if dimension == "combined" else {dimension}
        object_poses = (
            _sample_object_poses(rng, movable_ids, scene_info["layout"], profile)
            if "object_pose" in enabled
            else {}
        )
        table_height_offset = (
            rng.choice(profile.table_height_offsets)
            if table_ids and "table_height" in enabled
            else 0.0
        )
        light_config = (
            {
                "temperature": rng.choice(profile.light_temperatures),
                "intensity": rng.choice(profile.light_intensities),
            }
            if "lighting" in enabled
            else {}
        )
        table_appearance: dict[str, Any] = {}
        if table_ids and "table_appearance" in enabled:
            color = rng.choice(profile.table_colors)
            table_appearance = {
                "color": list(color),
                "color_name": _nearest_color_name(color),
                "roughness": rng.choice(profile.table_roughness),
                "metallic": rng.choice(profile.table_metallic),
            }
            if profile.table_textures:
                table_appearance["texture"] = rng.choice(profile.table_textures)
        specs.append(
            GenericScenarioSpec(
                instance_id=instance_id,
                dimension=dimension,
                scenario_seed=seed + instance_id,
                object_poses=object_poses,
                table_height_offset=table_height_offset,
                light_config=light_config,
                table_appearance=table_appearance,
            )
        )
    return specs


def _nearest_color_name(rgb: Iterable[float]) -> str:
    red, green, blue = rgb
    if max(rgb) - min(rgb) < 0.08:
        value = (red + green + blue) / 3
        return "black" if value < 0.25 else "gray" if value < 0.75 else "white"
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    if saturation < 0.15:
        return "gray"
    names = ("red", "yellow", "green", "cyan", "blue", "magenta")
    return names[int((hue * 6.0) + 0.5) % 6] if value >= 0.15 else "black"


def _number(value: float) -> str:
    value = 0.0 if abs(value) < 0.0000005 else value
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _copy_texture(texture: str, instance_dir: Path) -> str:
    source = Path(texture)
    asset_dir = instance_dir / "augmentation_assets"
    asset_dir.mkdir(exist_ok=True)
    destination = asset_dir / source.name
    shutil.copy2(source, destination)
    return f"./augmentation_assets/{destination.name}"


def _appearance_usd(
    spec: GenericScenarioSpec,
    table_ids: tuple[str, ...],
    instance_dir: Path,
) -> tuple[list[str], dict[str, Any]]:
    if not spec.table_appearance:
        return [], {}
    appearance = dict(spec.table_appearance)
    texture = appearance.get("texture")
    if texture:
        appearance["texture"] = _copy_texture(str(texture), instance_dir)
    color = appearance["color"]
    lines = [
        '        def Scope "Looks"',
        "        {",
        '            def Material "TableAugmentationMaterial"',
        "            {",
        '                token outputs:surface.connect = </World/Augmentation/Looks/TableAugmentationMaterial/Surface.outputs:surface>',
        '                def Shader "Surface"',
        "                {",
        '                    uniform token info:id = "UsdPreviewSurface"',
    ]
    if appearance.get("texture"):
        lines.append(
            '                    color3f inputs:diffuseColor.connect = </World/Augmentation/Looks/TableAugmentationMaterial/Texture.outputs:rgb>'
        )
    else:
        lines.append(
            "                    color3f inputs:diffuseColor = "
            f"({_number(color[0])}, {_number(color[1])}, {_number(color[2])})"
        )
    lines.extend(
        [
            f"                    float inputs:metallic = {_number(appearance['metallic'])}",
            f"                    float inputs:roughness = {_number(appearance['roughness'])}",
            "                    token outputs:surface",
            "                }",
        ]
    )
    if appearance.get("texture"):
        lines.extend(
            [
                '                def Shader "PrimvarReader"',
                "                {",
                '                    uniform token info:id = "UsdPrimvarReader_float2"',
                '                    token inputs:varname = "st"',
                "                    float2 outputs:result",
                "                }",
                '                def Shader "Texture"',
                "                {",
                '                    uniform token info:id = "UsdUVTexture"',
                f"                    asset inputs:file = @{appearance['texture']}@",
                '                    float2 inputs:st.connect = </World/Augmentation/Looks/TableAugmentationMaterial/PrimvarReader.outputs:result>',
                '                    token inputs:sourceColorSpace = "sRGB"',
                "                    float3 outputs:rgb",
                "                }",
            ]
        )
    lines.extend(["            }", "        }"])
    return lines, appearance


def render_override_usda(
    spec: GenericScenarioSpec,
    scene_info: dict[str, Any],
    profile: AugmentationProfile,
    instance_dir: Path,
) -> tuple[str, dict[str, Any]]:
    movable_ids, table_ids, follow_ids = discover_object_ids(scene_info, profile)
    del movable_ids
    translations: dict[str, list[float]] = {
        object_id: list(values["xyz"])
        for object_id, values in spec.object_poses.items()
    }
    orientations = {
        object_id: list(values["xyzw"])
        for object_id, values in spec.object_poses.items()
    }
    if spec.table_height_offset:
        for object_id in (*table_ids, *follow_ids):
            base_xyz = scene_info["layout"][object_id].get("xyz")
            if not isinstance(base_xyz, list) or len(base_xyz) != 3:
                raise ValueError(f"layout.{object_id}.xyz must contain three numbers")
            xyz = translations.get(object_id, [float(item) for item in base_xyz])
            xyz[2] = float(base_xyz[2]) + spec.table_height_offset
            translations[object_id] = xyz

    lines = [
        "#usda 1.0",
        "(",
        '    defaultPrim = "World"',
        "    metersPerUnit = 1",
        "    subLayers = [@./scene_source.usda@]",
        '    upAxis = "Z"',
        ")",
        "",
        'over "World"',
        "{",
        '    over "Objects"',
        "    {",
    ]
    for object_id in sorted(set(translations) | set(orientations) | set(table_ids)):
        metadata = ""
        if spec.table_appearance and object_id in table_ids:
            metadata = ' (prepend apiSchemas = ["MaterialBindingAPI"])'
        lines.extend([f'        over "{object_id}"{metadata}', "        {"])
        if object_id in translations:
            xyz = translations[object_id]
            lines.append(
                "            double3 xformOp:translate = "
                f"({_number(xyz[0])}, {_number(xyz[1])}, {_number(xyz[2])})"
            )
        if object_id in orientations:
            x, y, z, w = orientations[object_id]
            lines.append(
                "            quatf xformOp:orient = "
                f"({_number(w)}, {_number(x)}, {_number(y)}, {_number(z)})"
            )
        if spec.table_appearance and object_id in table_ids:
            lines.extend(
                [
                    "            rel material:binding = </World/Augmentation/Looks/TableAugmentationMaterial> (",
                    '                bindMaterialAs = "strongerThanDescendants"',
                    "            )",
                ]
            )
        lines.append("        }")
    lines.extend(["    }", "", '    def Scope "Augmentation"', "    {"])
    appearance_lines, appearance = _appearance_usd(spec, table_ids, instance_dir)
    lines.extend(appearance_lines)
    lines.extend(["    }", "}", ""])
    return "\n".join(lines), appearance


def _update_scene_info(
    base: dict[str, Any],
    spec: GenericScenarioSpec,
    profile: AugmentationProfile,
    appearance: dict[str, Any],
) -> dict[str, Any]:
    payload = deepcopy(base)
    _, table_ids, follow_ids = discover_object_ids(payload, profile)
    for object_id, pose in spec.object_poses.items():
        payload["layout"][object_id]["xyz"] = pose["xyz"]
        payload["layout"][object_id]["xyzw"] = pose["xyzw"]
    if spec.table_height_offset:
        for object_id in (*table_ids, *follow_ids):
            payload["layout"][object_id]["xyz"][2] = round(
                float(base["layout"][object_id]["xyz"][2]) + spec.table_height_offset,
                6,
            )
    if appearance:
        for table_id in table_ids:
            description = payload["layout"][table_id].setdefault("description", {})
            description["color"] = appearance["color_name"]
            description["augmentation_material"] = {
                key: value for key, value in appearance.items() if key != "color_name"
            }
    payload["seed"] = spec.scenario_seed
    return payload


def _scenario_payload(
    source_dir: Path,
    spec: GenericScenarioSpec,
    appearance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "instance_id": spec.instance_id,
        "split": "augmented",
        "dimension": spec.dimension,
        "scenario_seed": spec.scenario_seed,
        "source_scene": str(source_dir),
        "light_config": spec.light_config,
        "parameters": {
            "object_poses": spec.object_poses,
            "table_height_offset": spec.table_height_offset,
            "table_appearance": appearance,
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clear_generated(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for path in output_dir.iterdir():
        if path.is_dir() and path.name.isdigit():
            shutil.rmtree(path)
    manifest = output_dir / "scenario_manifest.json"
    if manifest.exists():
        manifest.unlink()


def numeric_instance_ids(task_dir: Path) -> list[int]:
    """Return numeric scene directory IDs in ascending order."""
    task_dir = Path(task_dir)
    if not task_dir.is_dir():
        return []
    return sorted(
        int(path.name)
        for path in task_dir.iterdir()
        if path.is_dir() and path.name.isdigit()
    )


def _existing_manifest_payloads(output_dir: Path) -> list[dict[str, Any]]:
    manifest_path = output_dir / "scenario_manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    scenarios = manifest.get("scenarios", [])
    return [item for item in scenarios if isinstance(item, dict)]


def _copy_source_bundle(source_dir: Path, instance_dir: Path) -> None:
    shutil.copytree(source_dir, instance_dir)
    scene_path = instance_dir / "scene.usda"
    if not scene_path.is_file():
        raise FileNotFoundError(f"source scene is missing scene.usda: {source_dir}")
    source_layer = instance_dir / "scene_source.usda"
    if source_layer.is_file():
        # The selected source may itself be a previously augmented bundle.
        # Retain its underlying source layer instead of creating a self-referencing
        # override layer (`scene_source.usda` sublayering itself).
        scene_path.unlink()
    else:
        scene_path.replace(source_layer)
    for generated_name in ("scenario.json",):
        generated_path = instance_dir / generated_name
        if generated_path.exists():
            generated_path.unlink()


def generate_augmented_scenarios(
    source_dir: Path,
    output_dir: Path,
    *,
    count: int = 40,
    seed: int = 20260720,
    profile: AugmentationProfile | None = None,
    replace_generated: bool = False,
) -> list[GenericScenarioSpec]:
    """Augment one source bundle into deterministic numeric scenario bundles."""
    source_dir = Path(source_dir).resolve()
    output_dir = Path(output_dir).resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"source scene directory does not exist: {source_dir}")
    profile = profile or AugmentationProfile()

    existing_ids = numeric_instance_ids(output_dir)
    start_instance_id = 0 if replace_generated else (max(existing_ids) + 1 if existing_ids else 0)
    previous_payloads = [] if replace_generated else _existing_manifest_payloads(output_dir)

    with tempfile.TemporaryDirectory(prefix="geniesim-source-scene-") as staging_dir:
        staged_source = Path(staging_dir) / "source"
        shutil.copytree(source_dir, staged_source)
        scene_info = load_scene_info(staged_source)
        specs = build_generic_scenario_specs(
            scene_info,
            count,
            seed,
            profile,
            start_instance_id=start_instance_id,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        if replace_generated:
            _clear_generated(output_dir)

        scenario_payloads = []
        for spec in specs:
            instance_dir = output_dir / str(spec.instance_id)
            if instance_dir.exists():
                raise FileExistsError(f"refusing to overwrite existing scenario: {instance_dir}")
            _copy_source_bundle(staged_source, instance_dir)
            scene_text, appearance = render_override_usda(
                spec, scene_info, profile, instance_dir
            )
            (instance_dir / "scene.usda").write_text(scene_text, encoding="utf-8")
            _write_json(
                instance_dir / "scene_info.json",
                _update_scene_info(scene_info, spec, profile, appearance),
            )
            payload = _scenario_payload(source_dir, spec, appearance)
            _write_json(instance_dir / "scenario.json", payload)
            scenario_payloads.append(payload)

        _write_json(
            output_dir / "scenario_manifest.json",
            {
                "generator": "generic_llm_task_augmentation",
                "generator_version": GENERATOR_VERSION,
                "root_seed": seed,
                "source_scene": str(source_dir),
                "scenario_count": len(previous_payloads) + len(specs),
                "generated_instance_ids": [spec.instance_id for spec in specs],
                "existing_instance_ids_before_run": existing_ids,
                "scenarios": previous_payloads + scenario_payloads,
            },
        )
    return specs


def describe_scene(source_dir: Path, profile: AugmentationProfile | None = None) -> dict[str, Any]:
    """Return auto-discovered IDs for CLI inspection and profile authoring."""
    profile = profile or AugmentationProfile()
    scene_info = load_scene_info(source_dir)
    movable_ids, table_ids, follow_ids = discover_object_ids(scene_info, profile)
    return {
        "source_scene": str(Path(source_dir).resolve()),
        "movable_object_ids": list(movable_ids),
        "table_ids": list(table_ids),
        "move_with_table_ids": list(follow_ids),
    }
