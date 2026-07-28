#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Generate lightweight preview PNGs for background USD scenes.

This script does not require Isaac Sim rendering. It opens each USD stage with
pxr, extracts Mesh/Cube geometry, and draws a software isometric overview. The
intended use is asset browsing, not photorealistic validation.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-geniesim-preview")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from pxr import Gf, Usd, UsdGeom


SCENE_ENTRY_NAMES = ("background.usda", "background.usd", "scene.usd")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--background-root",
        type=Path,
        default=Path("/home/user/djy/geniesim_assets/background"),
        help="Root directory containing background scene assets.",
    )
    parser.add_argument(
        "--output-name",
        default="preview.png",
        help="PNG filename to write beside each scene USD.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Only render the first N scenes.")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument(
        "--max-faces",
        type=int,
        default=20000,
        help="Maximum mesh faces drawn per scene, sampled deterministically.",
    )
    parser.add_argument(
        "--include-common",
        action="store_true",
        help="Also include background/common assets. By default common shared assets are skipped.",
    )
    return parser.parse_args()


def discover_scenes(root: Path, include_common: bool) -> list[Path]:
    scenes: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name not in SCENE_ENTRY_NAMES:
            continue
        if not include_common and "common" in path.relative_to(root).parts:
            continue
        scenes.append(path)
    return scenes


def _matrix_transform(matrix: Gf.Matrix4d, point: Gf.Vec3d) -> tuple[float, float, float]:
    transformed = matrix.Transform(point)
    return float(transformed[0]), float(transformed[1]), float(transformed[2])


def _prim_color(prim: Usd.Prim) -> tuple[float, float, float]:
    attr = UsdGeom.Gprim(prim).GetDisplayColorAttr()
    if attr:
        value = attr.Get()
        if value:
            color = value[0]
            return tuple(float(max(0.0, min(1.0, c))) for c in color)

    digest = hashlib.sha1(str(prim.GetPath()).encode("utf-8")).digest()
    # Quiet but varied asset-browser palette.
    return (
        0.32 + digest[0] / 255.0 * 0.36,
        0.36 + digest[1] / 255.0 * 0.34,
        0.40 + digest[2] / 255.0 * 0.32,
    )


def _mesh_faces(prim: Usd.Prim, max_faces: int) -> list[tuple[list[tuple[float, float, float]], tuple[float, float, float]]]:
    mesh = UsdGeom.Mesh(prim)
    points = mesh.GetPointsAttr().Get()
    counts = mesh.GetFaceVertexCountsAttr().Get()
    indices = mesh.GetFaceVertexIndicesAttr().Get()
    if not points or not counts or not indices:
        return []

    matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    world_points = [_matrix_transform(matrix, Gf.Vec3d(p[0], p[1], p[2])) for p in points]
    color = _prim_color(prim)

    faces = []
    offset = 0
    for count in counts:
        count = int(count)
        if count >= 3:
            face_indices = indices[offset : offset + count]
            face = [world_points[int(i)] for i in face_indices]
            faces.append((face, color))
        offset += count

    if len(faces) > max_faces:
        stride = max(1, math.ceil(len(faces) / max_faces))
        faces = faces[::stride][:max_faces]
    return faces


def _cube_faces(prim: Usd.Prim) -> list[tuple[list[tuple[float, float, float]], tuple[float, float, float]]]:
    cube = UsdGeom.Cube(prim)
    size = float(cube.GetSizeAttr().Get() or 2.0)
    half = size / 2.0
    local_points = [
        (-half, -half, -half),
        (half, -half, -half),
        (half, half, -half),
        (-half, half, -half),
        (-half, -half, half),
        (half, -half, half),
        (half, half, half),
        (-half, half, half),
    ]
    face_indices = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    world_points = [_matrix_transform(matrix, Gf.Vec3d(*p)) for p in local_points]
    color = _prim_color(prim)
    return [([world_points[i] for i in face], color) for face in face_indices]


Face = tuple[list[tuple[float, float, float]], tuple[float, float, float]]


def extract_faces(stage: Usd.Stage, max_faces: int) -> list[Face]:
    faces = []
    remaining = max_faces
    for prim in stage.Traverse():
        if not prim.IsActive() or not prim.IsDefined():
            continue
        type_name = prim.GetTypeName()
        if type_name == "Mesh":
            mesh_faces = _mesh_faces(prim, remaining)
            faces.extend(mesh_faces)
            remaining = max(0, max_faces - len(faces))
            if remaining <= 0:
                break
        elif type_name == "Cube":
            faces.extend(_cube_faces(prim))
    return faces[:max_faces]


def _face_normal(face: list[tuple[float, float, float]]) -> np.ndarray:
    if len(face) < 3:
        return np.zeros(3)
    points = np.array(face[:3], dtype=float)
    normal = np.cross(points[1] - points[0], points[2] - points[0])
    length = np.linalg.norm(normal)
    if length <= 1e-9:
        return np.zeros(3)
    return normal / length


def filter_preview_faces(faces: list[Face], minimum: np.ndarray, maximum: np.ndarray) -> list[Face]:
    """Hide high horizontal caps so enclosed rooms show interior structure."""
    z_span = max(float(maximum[2] - minimum[2]), 1e-6)
    ceiling_z = float(minimum[2] + z_span * 0.55)
    filtered: list[Face] = []
    for face, color in faces:
        arr = np.array(face, dtype=float)
        center_z = float(arr[:, 2].mean())
        normal = _face_normal(face)
        mostly_horizontal = abs(float(normal[2])) > 0.65
        if mostly_horizontal and center_z > ceiling_z:
            continue
        filtered.append((face, color))
    return filtered or faces


def stage_range(stage: Usd.Stage) -> tuple[np.ndarray, np.ndarray]:
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
        useExtentsHint=True,
    )
    box_range = cache.ComputeWorldBound(stage.GetPseudoRoot()).ComputeAlignedRange()
    if box_range.IsEmpty():
        return np.array([-1.0, -1.0, -1.0]), np.array([1.0, 1.0, 1.0])
    return np.array(box_range.GetMin(), dtype=float), np.array(box_range.GetMax(), dtype=float)


def set_equal_axes(ax, minimum: np.ndarray, maximum: np.ndarray) -> None:
    center = (minimum + maximum) / 2.0
    radius = max(float(np.max(maximum - minimum)) / 2.0, 0.5)
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(max(0.0, center[2] - radius * 0.65), center[2] + radius * 0.85)


def draw_faces(ax, faces: list[Face], minimum: np.ndarray, maximum: np.ndarray, elev: float, azim: float) -> None:
    ax.set_facecolor("#f4f5f7")
    if faces:
        poly = Poly3DCollection(
            [face for face, _color in faces],
            facecolors=[color for _face, color in faces],
            edgecolors=(0.17, 0.18, 0.20, 0.22),
            linewidths=0.15,
            alpha=0.90,
        )
        ax.add_collection3d(poly)

    set_equal_axes(ax, minimum, maximum)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_box_aspect((1, 1, 0.55))


def render_scene(scene_path: Path, output_path: Path, width: int, height: int, max_faces: int, root: Path) -> None:
    stage = Usd.Stage.Open(str(scene_path))
    if stage is None:
        raise RuntimeError(f"Failed to open USD stage: {scene_path}")

    faces = extract_faces(stage, max_faces)
    minimum, maximum = stage_range(stage)
    preview_faces = filter_preview_faces(faces, minimum, maximum)

    fig = plt.figure(figsize=(width / 100.0, height / 100.0), dpi=100)
    fig.patch.set_facecolor("#f4f5f7")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.87, bottom=0.02, wspace=0.02)

    top_ax = fig.add_subplot(1, 2, 1, projection="3d")
    iso_ax = fig.add_subplot(1, 2, 2, projection="3d")
    draw_faces(top_ax, preview_faces, minimum, maximum, elev=78, azim=-90)
    draw_faces(iso_ax, preview_faces, minimum, maximum, elev=28, azim=-42)
    top_ax.set_title("Top overview", color="#373b42", fontsize=12, pad=2)
    iso_ax.set_title("Isometric overview", color="#373b42", fontsize=12, pad=2)

    rel = scene_path.parent.relative_to(root)
    fig.text(
        0.025,
        0.955,
        str(rel),
        fontsize=18,
        color="#15171a",
        weight="bold",
    )
    fig.text(
        0.025,
        0.918,
        f"{scene_path.name} | {len(preview_faces)} visible faces ({len(faces)} source faces)",
        fontsize=10,
        color="#555b63",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    root = args.background_root.expanduser().resolve()
    scenes = discover_scenes(root, args.include_common)
    if args.limit > 0:
        scenes = scenes[: args.limit]

    if not scenes:
        print(f"No scenes found under {root}")
        return 1

    for index, scene in enumerate(scenes, 1):
        output = scene.parent / args.output_name
        print(f"[{index}/{len(scenes)}] {scene} -> {output}")
        render_scene(scene, output, args.width, args.height, args.max_faces, root)
    print(f"Generated {len(scenes)} preview image(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
