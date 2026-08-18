#!/usr/bin/env python3
"""Convert data_collection saved-task JSON files into benchmark scene instances."""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


DEFAULT_TARGET_ID = "geniesim_2025_target_grasp_object"
DEFAULT_TABLE_ASSET = "objects/benchmark/table/benchmark_table_019"
USD_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return data


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def natural_key(path: Path) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def normalize_quaternion(quaternion: Sequence[float]) -> tuple[float, float, float, float]:
    if len(quaternion) != 4:
        raise ValueError(f"quaternion must contain four WXYZ values: {quaternion}")
    values = tuple(float(value) for value in quaternion)
    norm = math.sqrt(sum(value * value for value in values))
    if norm < 1e-12:
        raise ValueError("quaternion norm must be non-zero")
    return tuple(value / norm for value in values)  # type: ignore[return-value]


def quaternion_conjugate(quaternion: Sequence[float]) -> tuple[float, float, float, float]:
    w, x, y, z = normalize_quaternion(quaternion)
    return w, -x, -y, -z


def quaternion_multiply(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float, float]:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return (
        lw * rw - lx * rx - ly * ry - lz * rz,
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    )


def rotate_vector(quaternion: Sequence[float], vector: Sequence[float]) -> tuple[float, float, float]:
    q = normalize_quaternion(quaternion)
    rotated = quaternion_multiply(quaternion_multiply(q, (0.0, *vector)), quaternion_conjugate(q))
    return rotated[1], rotated[2], rotated[3]


def world_to_local_pose(
    position: Sequence[float],
    quaternion: Sequence[float],
    origin_position: Sequence[float],
    origin_quaternion: Sequence[float],
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    if len(position) != 3 or len(origin_position) != 3:
        raise ValueError("positions must contain three XYZ values")
    origin_inverse = quaternion_conjugate(origin_quaternion)
    delta = tuple(float(position[index]) - float(origin_position[index]) for index in range(3))
    local_position = rotate_vector(origin_inverse, delta)
    local_quaternion = normalize_quaternion(
        quaternion_multiply(origin_inverse, normalize_quaternion(quaternion))
    )
    return local_position, local_quaternion


def _rounded(values: Iterable[float], digits: int = 9) -> list[float]:
    return [round(float(value), digits) for value in values]


def _usd_number(value: float) -> str:
    value = float(value)
    if abs(value) < 5e-13:
        return "0"
    return format(value, ".12g")


def _usd_tuple(values: Sequence[float]) -> str:
    return "(" + ", ".join(_usd_number(value) for value in values) + ")"


def _validate_prim_name(name: str) -> None:
    if not USD_IDENTIFIER.fullmatch(name):
        raise ValueError(f"object_id is not a valid USD prim name: {name!r}")


def asset_relative_dir(data_info_dir: str) -> PurePosixPath:
    normalized = data_info_dir.replace("\\", "/").rstrip("/")
    marker = "/geniesim_assets/"
    if marker in normalized:
        normalized = normalized.split(marker, 1)[1]
    else:
        normalized = normalized.lstrip("/")
    relative = PurePosixPath(normalized)
    if not relative.parts or ".." in relative.parts:
        raise ValueError(f"invalid data_info_dir: {data_info_dir!r}")
    return relative


def asset_usd_path(asset_dir: Path) -> Path:
    for filename in ("Aligned.usda", "Aligned.usd"):
        candidate = asset_dir / filename
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"asset has neither Aligned.usda nor Aligned.usd: {asset_dir}")


def wrapper_entity_quaternion(asset_path: Path) -> tuple[float, float, float, float]:
    """Return the direct `entity` rotation applied by an Aligned.usda wrapper."""
    if asset_path.suffix != ".usda":
        return 1.0, 0.0, 0.0, 0.0

    text = asset_path.read_text(encoding="utf-8")
    marker = re.search(r'def\s+Xform\s+"entity"', text)
    if marker is None:
        return 1.0, 0.0, 0.0, 0.0
    block_start = text.find("{", marker.end())
    if block_start < 0:
        raise ValueError(f"malformed entity prim in asset wrapper: {asset_path}")

    depth = 1
    block_end = block_start + 1
    while block_end < len(text) and depth:
        if text[block_end] == "{":
            depth += 1
        elif text[block_end] == "}":
            depth -= 1
        block_end += 1
    if depth:
        raise ValueError(f"unterminated entity prim in asset wrapper: {asset_path}")

    block = text[block_start + 1 : block_end - 1]
    nested_prim = re.search(r"\n\s*(?:def|over)\s+", block)
    direct_properties = block[: nested_prim.start()] if nested_prim else block

    translate_match = re.search(r"xformOp:translate\s*=\s*\(([^)]+)\)", direct_properties)
    scale_match = re.search(r"xformOp:scale\s*=\s*\(([^)]+)\)", direct_properties)
    for match, expected, name in (
        (translate_match, (0.0, 0.0, 0.0), "translation"),
        (scale_match, (1.0, 1.0, 1.0), "scale"),
    ):
        if match is None:
            continue
        values = tuple(float(value.strip()) for value in match.group(1).split(","))
        if len(values) != 3 or any(abs(value - expected[index]) > 1e-8 for index, value in enumerate(values)):
            raise ValueError(
                f"unsupported non-identity entity {name} in asset wrapper: {asset_path}"
            )

    orient_match = re.search(r"quat[fd]\s+xformOp:orient\s*=\s*\(([^)]+)\)", direct_properties)
    if orient_match is None:
        return 1.0, 0.0, 0.0, 0.0
    values = tuple(float(value.strip()) for value in orient_match.group(1).split(","))
    return normalize_quaternion(values)


def compensate_asset_wrapper_pose(
    local_quaternion: Sequence[float], asset_path: Path
) -> tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]:
    """Choose a parent pose whose composed entity pose matches Aligned.usd."""
    entity_quaternion = wrapper_entity_quaternion(asset_path)
    parent_quaternion = normalize_quaternion(
        quaternion_multiply(
            normalize_quaternion(local_quaternion),
            quaternion_conjugate(entity_quaternion),
        )
    )
    return parent_quaternion, entity_quaternion


def runtime_asset_path(relative_dir: PurePosixPath, filename: str, runtime_root: str) -> str:
    return str(PurePosixPath(runtime_root) / relative_dir / filename)


def load_literal_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = ast.literal_eval(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def load_asset_description(asset_dir: Path, saved_object: dict[str, Any]) -> dict[str, Any]:
    description = load_literal_dict(asset_dir / "description.py")
    result = dict(description)
    semantic_name = saved_object.get("english_semantic_name") or saved_object.get("semantic_name")
    if semantic_name and not result.get("semantic_name"):
        result["semantic_name"] = [str(semantic_name)]
    elif isinstance(result.get("semantic_name"), str):
        result["semantic_name"] = [result["semantic_name"]]
    if saved_object.get("size"):
        result["dimensions"] = list(saved_object["size"])
    result.setdefault("unit", saved_object.get("unit", "m"))
    return result


def table_description(table_dir: Path) -> tuple[dict[str, Any], list[float]]:
    description = load_literal_dict(table_dir / "description.py")
    params = load_json(table_dir / "object_parameters.json")
    item = load_literal_dict(table_dir / "item.py")
    center_offset = [0.0, 0.0, 0.1]
    dimensions = [0.6, 1.0, 0.73]
    for shape in item.get("shapes", []):
        if shape.get("name") == "bbox":
            center_offset = [float(value) for value in shape.get("position", center_offset)]
            dimensions = [float(value) for value in shape.get("size", dimensions)]
            break
    result = dict(description)
    result.setdefault("semantic_name", [params.get("semantic_name", "table")])
    result.setdefault("object_category", ["furniture", "table"])
    result.setdefault("shape", "rectangular")
    result.setdefault("color", "white")
    result["dimensions"] = dimensions
    result.setdefault("unit", params.get("unit", "m"))
    return result, center_offset


def scale_vector(value: Any) -> tuple[float, float, float]:
    if isinstance(value, (int, float)):
        scalar = float(value)
        return scalar, scalar, scalar
    if isinstance(value, list) and len(value) == 3:
        return tuple(float(item) for item in value)  # type: ignore[return-value]
    raise ValueError(f"scale must be a number or three values: {value!r}")


def render_scene_usda(
    objects: list[dict[str, Any]],
    table: dict[str, Any],
    assets_root: Path,
    runtime_assets_root: str,
) -> str:
    entries = [table, *objects]
    lines = [
        "#usda 1.0",
        "(",
        '    defaultPrim = "World"',
        "    metersPerUnit = 1",
        '    upAxis = "Z"',
        ")",
        "",
        'def Xform "World"',
        "{",
        '    def Xform "Objects"',
        "    {",
    ]
    for entry in entries:
        object_id = entry["object_id"]
        _validate_prim_name(object_id)
        relative_dir = asset_relative_dir(entry["data_info_dir"])
        source_usd = asset_usd_path(assets_root / Path(*relative_dir.parts))
        payload = runtime_asset_path(relative_dir, source_usd.name, runtime_assets_root)
        position = entry["local_position"]
        quaternion = entry["local_quaternion"]
        scale = scale_vector(entry.get("scale", 1.0))
        lines.extend(
            [
                f'        def Xform "{object_id}" (',
                f"            prepend payload = @{payload}@",
                "        )",
                "        {",
                f"            quatf xformOp:orient = {_usd_tuple(quaternion)}",
                f"            float3 xformOp:scale = {_usd_tuple(scale)}",
                f"            double3 xformOp:translate = {_usd_tuple(position)}",
                '            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient", "xformOp:scale"]',
            ]
        )
        if entry.get("kinematic") or entry.get("mass") is not None:
            lines.extend(["", '            over "entity"', "            {"])
            if entry.get("kinematic"):
                lines.append("                bool physics:kinematicEnabled = 1")
            if entry.get("mass") is not None:
                lines.append(f"                float physics:mass = {_usd_number(entry['mass'])}")
            lines.append("            }")
        lines.extend(["        }", ""])
    lines.extend(["    }", "}", ""])
    return "\n".join(lines)


def object_keywords(saved_object: dict[str, Any], description: dict[str, Any], local_y: float) -> list[str]:
    keywords: list[str] = []
    semantic_name = saved_object.get("english_semantic_name") or saved_object.get("semantic_name")
    if semantic_name:
        keywords.append(str(semantic_name).replace("_", " "))
    categories = description.get("object_category", [])
    if isinstance(categories, str):
        categories = [categories]
    keywords.extend(str(value) for value in categories)
    keywords.append("left" if local_y >= 0 else "right")
    return list(dict.fromkeys(keywords))


def build_scene_info(
    objects: list[dict[str, Any]],
    table: dict[str, Any],
    assets_root: Path,
    task_id: str,
    instance_id: int,
    source_file: Path,
) -> dict[str, Any]:
    root_id = f"root_scene_dc_{instance_id}"
    group_id = f"{task_id}_dc_{instance_id}"
    layout: dict[str, Any] = {}
    nodes = [{"id": root_id}, {"id": group_id}]
    links = [{"source": root_id, "target": group_id}]

    table_relative = asset_relative_dir(table["data_info_dir"])
    table_dir = assets_root / Path(*table_relative.parts)
    table_desc, center_offset = table_description(table_dir)
    center_delta = rotate_vector(table["local_quaternion"], center_offset)
    table_xyz = [table["local_position"][index] + center_delta[index] for index in range(3)]
    table_keywords = ["table", "white", "furniture", "center"]
    table_tags = [root_id, group_id, table["object_id"]]
    layout[table["object_id"]] = {
        "description": table_desc,
        "keywords": table_keywords,
        "tags": table_tags,
        "usd": table_relative.name,
        "xyz": _rounded(table_xyz, 6),
        "xyzw": _rounded((*table["local_quaternion"][1:], table["local_quaternion"][0]), 6),
    }
    nodes.append({"id": table["object_id"], "tags": table_keywords})
    links.append({"source": group_id, "target": table["object_id"]})

    for entry in objects:
        relative_dir = asset_relative_dir(entry["data_info_dir"])
        asset_dir = assets_root / Path(*relative_dir.parts)
        description = load_asset_description(asset_dir, entry)
        keywords = object_keywords(entry, description, entry["local_position"][1])
        tags = [root_id, group_id, entry["object_id"]]
        quaternion = entry["local_quaternion"]
        layout[entry["object_id"]] = {
            "description": description,
            "keywords": keywords,
            "tags": tags,
            "usd": relative_dir.name,
            "xyz": _rounded(entry["local_position"], 6),
            "xyzw": _rounded((quaternion[1], quaternion[2], quaternion[3], quaternion[0]), 6),
        }
        nodes.append({"id": entry["object_id"], "tags": keywords})
        links.append({"source": group_id, "target": entry["object_id"]})

    return {
        "layout": layout,
        "relations": {
            "graph": {
                "directed": True,
                "graph": {"rankdir": "LR"},
                "links": links,
                "multigraph": False,
                "nodes": nodes,
            }
        },
        "scene_id": task_id,
        "source": {"format": "data_collection_saved_task", "file": str(source_file)},
    }


def display_name(saved_object: dict[str, Any]) -> str:
    name = saved_object.get("english_semantic_name") or saved_object.get("semantic_name")
    return str(name or saved_object["object_id"]).replace("_", " ").title()


def build_instructions(target: dict[str, Any], task_id: str, arm: str) -> dict[str, Any]:
    name = display_name(target)
    arm_name = arm.title()
    return {
        "instructions": [
            {
                "instruction": (
                    f"{arm_name} arm picks up the {name} on the table, "
                    f"{arm_name} arm straightens the {name} and returns it to the original position"
                )
            }
        ],
        "task_id": task_id,
    }


def derive_upright_threshold_degrees(source: dict[str, Any], target_id: str) -> float:
    rules = source.get("task_metric", {}).get("filter_rules", [])
    for rule in rules:
        if rule.get("rule_name") != "is_object_end_pose_up":
            continue
        params = rule.get("params", {})
        objects = params.get("objects", [])
        thresholds = params.get("thresholds", [])
        if target_id in objects and len(thresholds) > objects.index(target_id):
            return math.degrees(float(thresholds[objects.index(target_id)]))
    for stage in source.get("stages", []):
        for checker in stage.get("checker", []):
            params = checker.get("params", {})
            if checker.get("checker_name") == "local_axis_angle" and params.get("object_id") == target_id:
                return math.degrees(float(params["value"]))
    raise ValueError(f"cannot derive upright threshold for target {target_id!r}")


def unsupported_filter_rules(source: dict[str, Any]) -> list[str]:
    supported = {"is_object_end_pose_up"}
    rules = source.get("task_metric", {}).get("filter_rules", [])
    return sorted({str(rule.get("rule_name")) for rule in rules if rule.get("rule_name") not in supported})


def build_problems(
    target_id: str,
    arm: str,
    upright_threshold_degrees: float,
    follow_bbox: Sequence[float],
    follow_timeout: int,
    upright_timeout: int,
    task_id: str,
) -> dict[str, Any]:
    gripper = f"{arm}_gripper"
    bbox_text = "[" + ",".join(_usd_number(value) for value in follow_bbox) + "]"
    threshold_text = _usd_number(upright_threshold_degrees)
    return {
        "problem1": {
            "Acts": [
                {
                    "ActionList": [
                        {
                            "ActionSetWaitAny": [
                                {"Follow": f"{target_id}|{bbox_text}|{gripper}"},
                                {"StepOut": follow_timeout},
                            ]
                        },
                        {
                            "ActionSetWaitAny": [
                                {"Upright": f"{target_id}|{threshold_text}"},
                                {"StepOut": upright_timeout},
                            ]
                        },
                    ]
                }
            ],
            "Init": [],
            "Objects": [],
            "Problem": task_id,
        }
    }


def next_instance_id(output_task_dir: Path) -> int:
    ids = [int(path.name) for path in output_task_dir.iterdir() if path.is_dir() and path.name.isdigit()] if output_task_dir.is_dir() else []
    return max(ids, default=-1) + 1


def prepare_objects(
    source: dict[str, Any],
    origin_position: Sequence[float],
    origin_quaternion: Sequence[float],
    assets_root: Path,
) -> list[dict[str, Any]]:
    objects = source.get("objects")
    if not isinstance(objects, list) or not objects:
        raise ValueError("saved task has no objects")
    prepared = []
    seen_ids: set[str] = set()
    for saved_object in objects:
        object_id = str(saved_object["object_id"])
        _validate_prim_name(object_id)
        if object_id in seen_ids:
            raise ValueError(f"duplicate object_id: {object_id}")
        seen_ids.add(object_id)
        position, quaternion = world_to_local_pose(
            saved_object["position"], saved_object["quaternion"], origin_position, origin_quaternion
        )
        relative_dir = asset_relative_dir(saved_object["data_info_dir"])
        asset_path = asset_usd_path(assets_root / Path(*relative_dir.parts))
        parent_quaternion, entity_quaternion = compensate_asset_wrapper_pose(quaternion, asset_path)
        entry = dict(saved_object)
        entry["local_position"] = position
        entry["source_local_quaternion"] = quaternion
        entry["wrapper_entity_quaternion"] = entity_quaternion
        entry["local_quaternion"] = parent_quaternion
        prepared.append(entry)
    return prepared


def source_index(path: Path) -> int | None:
    matches = re.findall(r"(\d+)", path.stem)
    return int(matches[-1]) if matches else None


def convert_one(
    source_path: Path,
    output_dir: Path,
    instance_id: int,
    origin_position: Sequence[float],
    origin_quaternion: Sequence[float],
    assets_root: Path,
    runtime_assets_root: str,
    target_id: str,
    task_id: str,
    table_asset: str,
    table_local_position: Sequence[float],
    table_local_quaternion: Sequence[float],
    upright_threshold_degrees: float | None,
    follow_bbox: Sequence[float],
    follow_timeout: int,
    upright_timeout: int,
    force: bool,
) -> dict[str, Any]:
    source = load_json(source_path)
    objects = prepare_objects(source, origin_position, origin_quaternion, assets_root)
    targets = [entry for entry in objects if entry["object_id"] == target_id]
    if len(targets) != 1:
        raise ValueError(f"{source_path}: expected exactly one target {target_id!r}, found {len(targets)}")
    target = targets[0]
    arm = "left" if target["local_position"][1] >= 0 else "right"
    threshold = (
        float(upright_threshold_degrees)
        if upright_threshold_degrees is not None
        else derive_upright_threshold_degrees(source, target_id)
    )
    table = {
        "object_id": "data_collection_table",
        "data_info_dir": table_asset,
        "local_position": tuple(float(value) for value in table_local_position),
        "local_quaternion": normalize_quaternion(table_local_quaternion),
        "scale": 1.0,
        "kinematic": True,
    }
    generated = {
        "scene.usda": render_scene_usda(objects, table, assets_root, runtime_assets_root),
        "scene_info.json": dump_json(
            build_scene_info(objects, table, assets_root, task_id, instance_id, source_path)
        ),
        "instructions.json": dump_json(build_instructions(target, task_id, arm)),
        "problems.json": dump_json(
            build_problems(
                target_id,
                arm,
                threshold,
                follow_bbox,
                follow_timeout,
                upright_timeout,
                task_id,
            )
        ),
    }
    if output_dir.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing instance: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, contents in generated.items():
        (output_dir / filename).write_text(contents, encoding="utf-8")
    return {
        "source": str(source_path),
        "source_index": source_index(source_path),
        "instance_id": instance_id,
        "output": str(output_dir),
        "target_id": target_id,
        "target_local_position": _rounded(target["local_position"]),
        "target_source_quaternion_wxyz": _rounded(target["source_local_quaternion"]),
        "target_parent_quaternion_wxyz": _rounded(target["local_quaternion"]),
        "target_wrapper_entity_quaternion_wxyz": _rounded(target["wrapper_entity_quaternion"]),
        "arm": arm,
        "upright_threshold_degrees": threshold,
        "unsupported_filter_rules": unsupported_filter_rules(source),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-convert data_collection saved tasks into geniesim_benchmark llm_task instances."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-task-dir", type=Path, required=True)
    parser.add_argument("--source-template", type=Path, required=True, help="Task template containing origin pose")
    parser.add_argument("--assets-root", type=Path, required=True, help="Host path corresponding to /geniesim_assets")
    parser.add_argument("--runtime-assets-root", default="/geniesim_assets")
    parser.add_argument("--task-id", default="straighten_object")
    parser.add_argument("--target-id", default=DEFAULT_TARGET_ID)
    parser.add_argument("--start-instance", type=int)
    parser.add_argument("--origin-position", nargs=3, type=float)
    parser.add_argument("--origin-quaternion", nargs=4, type=float, metavar=("W", "X", "Y", "Z"))
    parser.add_argument("--table-asset", default=DEFAULT_TABLE_ASSET)
    parser.add_argument("--table-local-position", nargs=3, type=float, default=[0.01, 0.0, 0.2609])
    parser.add_argument(
        "--table-local-quaternion", nargs=4, type=float, default=[1.0, 0.0, 0.0, 0.0], metavar=("W", "X", "Y", "Z")
    )
    parser.add_argument("--upright-threshold-deg", type=float, help="Override source threshold; default converts source radians")
    parser.add_argument("--follow-bbox", nargs=3, type=float, default=[0.2, 0.2, 0.2])
    parser.add_argument("--follow-timeout", type=int, default=200)
    parser.add_argument("--upright-timeout", type=int, default=300)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_files = sorted(args.input_dir.glob("*.json"), key=natural_key)
    if not input_files:
        raise FileNotFoundError(f"no JSON files found in {args.input_dir}")
    template = load_json(args.source_template)
    origin = template.get("origin", {})
    origin_position = args.origin_position or origin.get("position")
    origin_quaternion = args.origin_quaternion or origin.get("quaternion")
    if origin_position is None or origin_quaternion is None:
        raise ValueError("origin pose is missing; provide it in --source-template or via --origin-*")
    start_instance = args.start_instance if args.start_instance is not None else next_instance_id(args.output_task_dir)
    planned = [(source, start_instance + index) for index, source in enumerate(input_files)]
    collisions = [str(args.output_task_dir / str(instance_id)) for _, instance_id in planned if (args.output_task_dir / str(instance_id)).exists()]
    if collisions and not args.force:
        raise FileExistsError("refusing to overwrite existing instances: " + ", ".join(collisions))
    if args.dry_run:
        print(f"input files: {len(planned)}")
        for source, instance_id in planned:
            print(f"{source} -> {args.output_task_dir / str(instance_id)}")
        return 0

    records = []
    for source, instance_id in planned:
        record = convert_one(
            source_path=source,
            output_dir=args.output_task_dir / str(instance_id),
            instance_id=instance_id,
            origin_position=origin_position,
            origin_quaternion=origin_quaternion,
            assets_root=args.assets_root,
            runtime_assets_root=args.runtime_assets_root,
            target_id=args.target_id,
            task_id=args.task_id,
            table_asset=args.table_asset,
            table_local_position=args.table_local_position,
            table_local_quaternion=args.table_local_quaternion,
            upright_threshold_degrees=args.upright_threshold_deg,
            follow_bbox=args.follow_bbox,
            follow_timeout=args.follow_timeout,
            upright_timeout=args.upright_timeout,
            force=args.force,
        )
        records.append(record)
        omitted = record["unsupported_filter_rules"]
        suffix = f"; omitted rules: {', '.join(omitted)}" if omitted else ""
        print(f"converted {source.name} -> instance {instance_id} ({record['arm']} arm){suffix}")

    end_instance = records[-1]["instance_id"]
    manifest_path = args.output_task_dir / f"conversion_manifest_{start_instance}_{end_instance}.json"
    manifest = {
        "converter": Path(__file__).name,
        "source_template": str(args.source_template),
        "origin": {
            "position": [float(value) for value in origin_position],
            "quaternion_wxyz": list(normalize_quaternion(origin_quaternion)),
        },
        "records": records,
        "notes": [
            "Source world poses were converted into the template-origin local frame.",
            "Aligned.usda entity rotations are compensated so composed rigid-body poses match data_collection Aligned.usd poses.",
            "is_gripper_in_view is not emitted because benchmark ADER has no equivalent checker.",
            "Upright thresholds are converted from source radians to benchmark degrees unless overridden.",
        ],
    }
    manifest_path.write_text(dump_json(manifest), encoding="utf-8")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
