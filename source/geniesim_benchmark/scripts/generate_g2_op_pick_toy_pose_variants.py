#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Generate deterministic blue-block XY and yaw variants for g2_op_pick_toy."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


GENERATOR_NAME = "g2_op_pick_toy_blue_block_pose"
GENERATOR_VERSION = 1
DEFAULT_ROOT_SEED = 20260805


def _pair(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must be a two-element JSON array")
    low, high = float(value[0]), float(value[1])
    if low > high:
        raise ValueError(f"{name} lower bound must not exceed upper bound")
    return low, high


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{name} must be an array of non-empty strings")
    return tuple(value)


@dataclass(frozen=True)
class PlanarBounds:
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    def distance_to_point(self, x: float, y: float) -> float:
        dx = max(self.min_x - x, 0.0, x - self.max_x)
        dy = max(self.min_y - y, 0.0, y - self.max_y)
        return math.hypot(dx, dy)

    def contains_circle(self, x: float, y: float, radius: float) -> bool:
        return (
            self.min_x + radius <= x <= self.max_x - radius
            and self.min_y + radius <= y <= self.max_y - radius
        )


@dataclass(frozen=True)
class ObstacleBounds:
    prim_path: str
    bounds: PlanarBounds


@dataclass(frozen=True)
class SceneGeometry:
    target_prim_path: str
    target_parent_path: str
    baseline_world_xyz: tuple[float, float, float]
    baseline_world_yaw_deg: float
    parent_world_xyz: tuple[float, float, float]
    parent_world_yaw_deg: float
    target_planar_radius: float
    support_bounds: PlanarBounds
    obstacles: tuple[ObstacleBounds, ...]


@dataclass(frozen=True)
class PoseProfile:
    target_prim_path: str
    source_background_usd: str
    variant_asset_dir: str
    x_offset_range_m: tuple[float, float]
    y_offset_range_m: tuple[float, float]
    yaw_offset_range_deg: tuple[float, float]
    min_clearance_m: float
    min_planar_offset_m: float
    support_prim_path: str
    ignore_collision_prim_paths: tuple[str, ...]
    max_sampling_attempts: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PoseProfile":
        if not isinstance(payload, dict):
            raise ValueError("profile root must be a JSON object")
        profile = cls(
            target_prim_path=str(payload.get("target_prim_path", "")),
            source_background_usd=str(payload.get("source_background_usd", "")),
            variant_asset_dir=str(payload.get("variant_asset_dir", "")),
            x_offset_range_m=_pair(
                payload.get("x_offset_range_m"), "x_offset_range_m"
            ),
            y_offset_range_m=_pair(
                payload.get("y_offset_range_m"), "y_offset_range_m"
            ),
            yaw_offset_range_deg=_pair(
                payload.get("yaw_offset_range_deg"), "yaw_offset_range_deg"
            ),
            min_clearance_m=float(payload.get("min_clearance_m", 0.0)),
            min_planar_offset_m=float(payload.get("min_planar_offset_m", 0.0)),
            support_prim_path=str(payload.get("support_prim_path", "")),
            ignore_collision_prim_paths=_string_tuple(
                payload.get("ignore_collision_prim_paths", []),
                "ignore_collision_prim_paths",
            ),
            max_sampling_attempts=int(payload.get("max_sampling_attempts", 1000)),
        )
        for name in (
            "target_prim_path",
            "source_background_usd",
            "variant_asset_dir",
            "support_prim_path",
        ):
            if not getattr(profile, name):
                raise ValueError(f"{name} must be a non-empty string")
        if Path(profile.source_background_usd).is_absolute():
            raise ValueError("source_background_usd must be relative to the assets root")
        if Path(profile.variant_asset_dir).is_absolute():
            raise ValueError("variant_asset_dir must be relative to the assets root")
        if profile.min_clearance_m < 0 or profile.min_planar_offset_m < 0:
            raise ValueError("clearance and minimum offset must be non-negative")
        if profile.max_sampling_attempts < 1:
            raise ValueError("max_sampling_attempts must be positive")
        return profile


@dataclass(frozen=True)
class PoseVariant:
    instance_id: int
    scenario_seed: int
    x_offset_m: float
    y_offset_m: float
    yaw_offset_deg: float
    world_xyz: tuple[float, float, float]
    world_yaw_deg: float
    local_xyz: tuple[float, float, float]
    local_yaw_deg: float
    min_obstacle_clearance_m: float


def load_profile(path: Path) -> PoseProfile:
    return PoseProfile.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _normalize_angle_deg(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def xyzw_from_yaw_deg(yaw_deg: float) -> tuple[float, float, float, float]:
    half = math.radians(yaw_deg) / 2.0
    return (0.0, 0.0, math.sin(half), math.cos(half))


def world_to_parent_local(
    world_xyz: tuple[float, float, float],
    parent_world_xyz: tuple[float, float, float],
    parent_world_yaw_deg: float,
) -> tuple[float, float, float]:
    dx = world_xyz[0] - parent_world_xyz[0]
    dy = world_xyz[1] - parent_world_xyz[1]
    yaw = math.radians(parent_world_yaw_deg)
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    return (
        cos_yaw * dx + sin_yaw * dy,
        -sin_yaw * dx + cos_yaw * dy,
        world_xyz[2] - parent_world_xyz[2],
    )


def parent_local_to_world(
    local_xyz: tuple[float, float, float],
    parent_world_xyz: tuple[float, float, float],
    parent_world_yaw_deg: float,
) -> tuple[float, float, float]:
    yaw = math.radians(parent_world_yaw_deg)
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    return (
        parent_world_xyz[0] + cos_yaw * local_xyz[0] - sin_yaw * local_xyz[1],
        parent_world_xyz[1] + sin_yaw * local_xyz[0] + cos_yaw * local_xyz[1],
        parent_world_xyz[2] + local_xyz[2],
    )


def _minimum_clearance(
    x: float, y: float, geometry: SceneGeometry
) -> float:
    if not geometry.obstacles:
        return math.inf
    return min(
        obstacle.bounds.distance_to_point(x, y) - geometry.target_planar_radius
        for obstacle in geometry.obstacles
    )


def sample_pose_variant(
    geometry: SceneGeometry,
    profile: PoseProfile,
    scenario_seed: int,
    instance_id: int = -1,
) -> PoseVariant:
    if geometry.target_prim_path != profile.target_prim_path:
        raise ValueError(
            f"profile target {profile.target_prim_path} does not match inspected target "
            f"{geometry.target_prim_path}"
        )
    rng = random.Random(scenario_seed)
    for _ in range(profile.max_sampling_attempts):
        x_offset = rng.uniform(*profile.x_offset_range_m)
        y_offset = rng.uniform(*profile.y_offset_range_m)
        if math.hypot(x_offset, y_offset) < profile.min_planar_offset_m:
            continue
        yaw_offset = rng.uniform(*profile.yaw_offset_range_deg)
        world_xyz = (
            geometry.baseline_world_xyz[0] + x_offset,
            geometry.baseline_world_xyz[1] + y_offset,
            geometry.baseline_world_xyz[2],
        )
        if not geometry.support_bounds.contains_circle(
            world_xyz[0], world_xyz[1], geometry.target_planar_radius
        ):
            continue
        clearance = _minimum_clearance(world_xyz[0], world_xyz[1], geometry)
        if clearance < profile.min_clearance_m:
            continue
        world_yaw = _normalize_angle_deg(
            geometry.baseline_world_yaw_deg + yaw_offset
        )
        local_xyz = world_to_parent_local(
            world_xyz, geometry.parent_world_xyz, geometry.parent_world_yaw_deg
        )
        return PoseVariant(
            instance_id=instance_id,
            scenario_seed=scenario_seed,
            x_offset_m=x_offset,
            y_offset_m=y_offset,
            yaw_offset_deg=yaw_offset,
            world_xyz=world_xyz,
            world_yaw_deg=world_yaw,
            local_xyz=local_xyz,
            local_yaw_deg=_normalize_angle_deg(
                world_yaw - geometry.parent_world_yaw_deg
            ),
            min_obstacle_clearance_m=clearance,
        )
    raise RuntimeError(
        f"could not sample a safe target pose after {profile.max_sampling_attempts} "
        "attempts; reduce the offset range/clearance or inspect the support geometry"
    )


def _yaw_from_quaternion(quaternion: Any, label: str) -> float:
    imaginary = quaternion.GetImaginary()
    if abs(float(imaginary[0])) > 1e-5 or abs(float(imaginary[1])) > 1e-5:
        raise ValueError(f"{label} has roll/pitch; this XY+yaw generator requires Z-only rotation")
    return _normalize_angle_deg(
        math.degrees(
            2.0 * math.atan2(float(imaginary[2]), float(quaternion.GetReal()))
        )
    )


def _planar_bounds(bbox_cache: Any, prim: Any) -> PlanarBounds | None:
    aligned = bbox_cache.ComputeWorldBound(prim).ComputeAlignedBox()
    if aligned.IsEmpty():
        return None
    minimum = aligned.GetMin()
    maximum = aligned.GetMax()
    return PlanarBounds(
        float(minimum[0]),
        float(maximum[0]),
        float(minimum[1]),
        float(maximum[1]),
    )


def inspect_scene_geometry(
    background_path: Path, profile: PoseProfile
) -> SceneGeometry:
    try:
        from pxr import Gf, Usd, UsdGeom
    except ImportError as exc:
        raise RuntimeError(
            "OpenUSD Python bindings are required. Run this script with "
            "`conda run -n geniesim python ...`."
        ) from exc

    stage = Usd.Stage.Open(str(background_path))
    if stage is None:
        raise ValueError(f"could not open background USD: {background_path}")
    target = stage.GetPrimAtPath(profile.target_prim_path)
    if not target.IsValid():
        raise ValueError(f"target prim does not exist: {profile.target_prim_path}")
    support = stage.GetPrimAtPath(profile.support_prim_path)
    if not support.IsValid():
        raise ValueError(f"support prim does not exist: {profile.support_prim_path}")

    parent = target.GetParent()
    xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    target_transform = Gf.Transform(xform_cache.GetLocalToWorldTransform(target))
    parent_transform = Gf.Transform(xform_cache.GetLocalToWorldTransform(parent))
    target_translation = target_transform.GetTranslation()
    parent_translation = parent_transform.GetTranslation()

    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
    )
    target_box = bbox_cache.ComputeWorldBound(target).ComputeAlignedBox()
    target_size = target_box.GetSize()
    target_radius = math.hypot(float(target_size[0]), float(target_size[1])) / 2.0
    support_bounds = _planar_bounds(bbox_cache, support)
    if support_bounds is None:
        raise ValueError(f"support prim has no world bounds: {profile.support_prim_path}")

    ignored = set(profile.ignore_collision_prim_paths) | {
        profile.target_prim_path,
        profile.support_prim_path,
    }
    obstacles = []
    for sibling in parent.GetChildren():
        sibling_path = str(sibling.GetPath())
        if sibling_path in ignored:
            continue
        bounds = _planar_bounds(bbox_cache, sibling)
        if bounds is not None:
            obstacles.append(ObstacleBounds(sibling_path, bounds))

    return SceneGeometry(
        target_prim_path=profile.target_prim_path,
        target_parent_path=str(parent.GetPath()),
        baseline_world_xyz=tuple(float(value) for value in target_translation),
        baseline_world_yaw_deg=_yaw_from_quaternion(
            target_transform.GetRotation().GetQuat(), "target"
        ),
        parent_world_xyz=tuple(float(value) for value in parent_translation),
        parent_world_yaw_deg=_yaw_from_quaternion(
            parent_transform.GetRotation().GetQuat(), "target parent"
        ),
        target_planar_radius=target_radius,
        support_bounds=support_bounds,
        obstacles=tuple(obstacles),
    )


def _number(value: float) -> str:
    value = 0.0 if abs(value) < 0.0000000005 else value
    return f"{value:.9f}".rstrip("0").rstrip(".")


def _render_background_wrapper(
    variant: PoseVariant, source_reference: str
) -> str:
    local_quaternion = xyzw_from_yaw_deg(variant.local_yaw_deg)
    x, y, z, w = local_quaternion
    tx, ty, tz = variant.local_xyz
    return f'''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World" (
    prepend references = @{source_reference}@</World>
)
{{
    over "toyscene"
    {{
        over "Objects"
        {{
            over "blue_block"
            {{
                double3 xformOp:translate = ({_number(tx)}, {_number(ty)}, {_number(tz)})
                quatf xformOp:orient = ({_number(w)}, {_number(x)}, {_number(y)}, {_number(z)})
                uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]
            }}
        }}
    }}
}}
'''


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _variant_payload(
    variant: PoseVariant,
    profile: PoseProfile,
    geometry: SceneGeometry,
    background_usd: str,
) -> dict[str, Any]:
    return {
        "instance_id": variant.instance_id,
        "split": "pose_randomization",
        "dimension": "object_pose",
        "generator": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "scenario_seed": variant.scenario_seed,
        "background_usd": background_usd,
        "light_config": {},
        "parameters": {
            "target_prim_path": profile.target_prim_path,
            "x_offset_m": variant.x_offset_m,
            "y_offset_m": variant.y_offset_m,
            "yaw_offset_deg": variant.yaw_offset_deg,
            "world_xyz": list(variant.world_xyz),
            "world_yaw_deg": variant.world_yaw_deg,
            "local_xyz": list(variant.local_xyz),
            "local_yaw_deg": variant.local_yaw_deg,
            "target_planar_radius_m": geometry.target_planar_radius,
            "min_obstacle_clearance_m": variant.min_obstacle_clearance_m,
        },
    }


def generate_pose_variants(
    *,
    task_dir: Path,
    source_instance_dir: Path,
    assets_root: Path,
    profile: PoseProfile,
    geometry: SceneGeometry,
    count: int,
    root_seed: int,
    start_instance_id: int,
) -> list[PoseVariant]:
    task_dir = Path(task_dir).resolve()
    source_instance_dir = Path(source_instance_dir).resolve()
    assets_root = Path(assets_root).resolve()
    if count < 1:
        raise ValueError("count must be positive")
    if start_instance_id < 1:
        raise ValueError("start_instance_id must be at least 1; instance 0 is the baseline")
    if not source_instance_dir.is_dir():
        raise FileNotFoundError(f"source instance does not exist: {source_instance_dir}")
    source_background = assets_root / profile.source_background_usd
    if not source_background.is_file():
        raise FileNotFoundError(f"source background does not exist: {source_background}")

    instance_ids = list(range(start_instance_id, start_instance_id + count))
    variant_dir = assets_root / profile.variant_asset_dir
    for instance_id in instance_ids:
        instance_path = task_dir / str(instance_id)
        wrapper_path = variant_dir / f"{instance_id}.usda"
        if instance_path.exists():
            raise FileExistsError(f"refusing to overwrite task instance {instance_id}: {instance_path}")
        if wrapper_path.exists():
            raise FileExistsError(f"refusing to overwrite background wrapper: {wrapper_path}")

    variants = [
        replace(
            sample_pose_variant(
                geometry,
                profile,
                scenario_seed=root_seed + instance_id,
                instance_id=instance_id,
            ),
            instance_id=instance_id,
        )
        for instance_id in instance_ids
    ]
    variant_dir.mkdir(parents=True, exist_ok=True)
    source_reference = Path(
        os.path.relpath(source_background, start=variant_dir)
    ).as_posix()

    manifest_variants = []
    for variant in variants:
        background_usd = (
            Path(profile.variant_asset_dir) / f"{variant.instance_id}.usda"
        ).as_posix()
        wrapper_path = assets_root / background_usd
        wrapper_path.write_text(
            _render_background_wrapper(variant, source_reference), encoding="utf-8"
        )

        instance_dir = task_dir / str(variant.instance_id)
        shutil.copytree(source_instance_dir, instance_dir)
        scene_info_path = instance_dir / "scene_info.json"
        scene_info = json.loads(scene_info_path.read_text(encoding="utf-8"))
        target_info = scene_info["layout"]["blue_block"]
        target_info["xyz"] = [round(value, 6) for value in variant.world_xyz]
        target_info["xyzw"] = [
            round(value, 6) for value in xyzw_from_yaw_deg(variant.world_yaw_deg)
        ]
        scene_info["seed"] = variant.scenario_seed
        _write_json(scene_info_path, scene_info)

        scenario = _variant_payload(variant, profile, geometry, background_usd)
        _write_json(instance_dir / "scenario.json", scenario)
        manifest_variants.append(scenario)

    _write_json(
        task_dir / "blue_block_pose_manifest.json",
        {
            "generator": GENERATOR_NAME,
            "generator_version": GENERATOR_VERSION,
            "root_seed": root_seed,
            "source_instance": str(source_instance_dir),
            "source_background_usd": profile.source_background_usd,
            "generated_instance_ids": instance_ids,
            "profile": asdict(profile),
            "geometry": asdict(geometry),
            "variants": manifest_variants,
        },
    )
    return variants


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_task_dir() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "geniesim_benchmark"
        / "benchmark"
        / "config"
        / "llm_task"
        / "g2_op_pick_toy"
    )


def _default_assets_root() -> Path:
    configured = os.environ.get("GENIESIM_ASSETS_ROOT") or os.environ.get(
        "GENIESIM_ASSETS_SRC"
    )
    if configured:
        return Path(configured).expanduser()
    candidates = (Path("/geniesim_assets"), _repo_root().parent / "geniesim_assets")
    return next((path for path in candidates if path.is_dir()), candidates[-1])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, default=_default_task_dir())
    parser.add_argument("--source-instance", type=int, default=0)
    parser.add_argument("--assets-root", type=Path, default=_default_assets_root())
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path(__file__).resolve().parent
        / "profiles"
        / "g2_op_pick_toy_blue_block_pose.json",
    )
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=DEFAULT_ROOT_SEED)
    parser.add_argument("--start-instance", type=int, default=1)
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Print measured target/support/obstacle geometry without writing variants.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    profile = load_profile(args.profile)
    assets_root = args.assets_root.expanduser().resolve()
    background_path = assets_root / profile.source_background_usd
    geometry = inspect_scene_geometry(background_path, profile)
    if args.inspect_only:
        print(json.dumps(asdict(geometry), indent=2, sort_keys=True))
        return 0

    task_dir = args.task_dir.expanduser().resolve()
    variants = generate_pose_variants(
        task_dir=task_dir,
        source_instance_dir=task_dir / str(args.source_instance),
        assets_root=assets_root,
        profile=profile,
        geometry=geometry,
        count=args.count,
        root_seed=args.seed,
        start_instance_id=args.start_instance,
    )
    ids = ",".join(str(variant.instance_id) for variant in variants)
    print(f"Generated {len(variants)} blue-block pose variants: {ids}")
    print(f"Task instances: {task_dir}")
    print(f"Background wrappers: {assets_root / profile.variant_asset_dir}")
    print(
        "Run: geniesim benchmark run g2op_robust_g2_op_pick_toy_posegen.yaml "
        f"--benchmark.instance_ids={ids}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
