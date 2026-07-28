#!/usr/bin/env python3
"""Render lit Isaac Sim previews for background USD scenes.

Run this script with Isaac Sim's Python environment, for example:

    python render_background_scenes_isaac.py

The script edits only the in-memory stage and writes PNG files next to the
source background USD files.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path


DEFAULT_SCENES = (
    "/home/user/djy/geniesim_assets/background/home/home_1/background.usda",
    "/home/user/djy/geniesim_assets/background/home/home_2/background.usda",
    "/home/user/djy/geniesim_assets/background/home/home_3/background.usda",
)

carb = None
Gf = None
Sdf = None
Usd = None
UsdGeom = None
UsdLux = None
SIMULATION_APP = None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scene",
        action="append",
        default=[],
        help="Path to a background USD scene. Can be repeated.",
    )
    parser.add_argument(
        "--output-name",
        default="preview_isaac.png",
        help="Output file name written beside each USD scene.",
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Start SimulationApp in headless mode when not already running inside Kit.",
    )
    parser.add_argument(
        "--renderer",
        default="RayTracedLighting",
        help="SimulationApp renderer used when launching directly.",
    )
    parser.add_argument(
        "--settle-frames",
        type=int,
        default=80,
        help="Frames to update after loading each scene before capture.",
    )
    parser.add_argument(
        "--quit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Quit Isaac Sim when rendering is finished.",
    )
    return parser.parse_args(argv)


def script_args() -> list[str]:
    """Return arguments passed after this script path by Kit --exec."""

    argv = sys.argv[1:]
    this_file = Path(__file__).resolve()
    for index, item in enumerate(argv):
        try:
            if Path(item).resolve() == this_file:
                return argv[index + 1 :]
        except OSError:
            continue
    return argv


def load_runtime_modules() -> None:
    global carb, Gf, Sdf, Usd, UsdGeom, UsdLux

    import carb as carb_module
    from pxr import Gf as Gf_module
    from pxr import Sdf as Sdf_module
    from pxr import Usd as Usd_module
    from pxr import UsdGeom as UsdGeom_module
    from pxr import UsdLux as UsdLux_module

    import omni.kit.app  # noqa: F401
    import omni.usd  # noqa: F401

    carb = carb_module
    Gf = Gf_module
    Sdf = Sdf_module
    Usd = Usd_module
    UsdGeom = UsdGeom_module
    UsdLux = UsdLux_module


def get_running_app():
    try:
        import omni.kit.app

        return omni.kit.app.get_app()
    except Exception:
        return None


def maybe_launch_simulation_app(args: argparse.Namespace):
    app = get_running_app()
    if app is not None:
        return None

    from isaacsim import SimulationApp

    if SimulationApp is None:
        raise RuntimeError("isaacsim.SimulationApp is not available in this Python environment")

    return SimulationApp(
        {
            "headless": args.headless,
            "renderer": args.renderer,
            "width": args.width,
            "height": args.height,
        }
    )


def wait_frames(count: int) -> None:
    import omni.kit.app

    app = omni.kit.app.get_app()
    for _ in range(max(0, count)):
        if SIMULATION_APP is not None:
            SIMULATION_APP.update()
        else:
            app.update()


def configure_rendering(width: int, height: int) -> None:
    settings = carb.settings.get_settings()
    settings.set("/renderer/enabled", "rtx")
    settings.set("/renderer/active", "rtx")
    settings.set("/rtx/materialDb/syncLoads", True)
    settings.set("/rtx/hydra/materialSyncLoads", True)
    settings.set("/rtx-transient/resourcemanager/enableTextureStreaming", False)
    settings.set("/rtx/ecoMode/enabled", False)
    settings.set("/app/captureFrame/setAlphaTo1", True)
    settings.set("/app/viewport/grid/enabled", False)
    settings.set("/persistent/app/viewport/displayOptions", 0)
    settings.set("/app/window/width", width)
    settings.set("/app/window/height", height)


def combined_stage_bounds(stage: Usd.Stage) -> tuple[Gf.Vec3d, Gf.Vec3d]:
    purposes = [
        UsdGeom.Tokens.default_,
        UsdGeom.Tokens.render,
        UsdGeom.Tokens.proxy,
    ]
    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        purposes,
        useExtentsHint=True,
        ignoreVisibility=False,
    )

    minimum = None
    maximum = None
    for prim in stage.GetPseudoRoot().GetChildren():
        name = prim.GetName()
        if name.startswith("Preview"):
            continue
        if not prim.IsActive():
            continue
        try:
            aligned = bbox_cache.ComputeWorldBound(prim).ComputeAlignedBox()
        except Exception:
            continue
        if aligned.IsEmpty():
            continue
        min_pt = aligned.GetMin()
        max_pt = aligned.GetMax()
        if minimum is None:
            minimum = Gf.Vec3d(min_pt)
            maximum = Gf.Vec3d(max_pt)
        else:
            minimum = Gf.Vec3d(
                min(minimum[0], min_pt[0]),
                min(minimum[1], min_pt[1]),
                min(minimum[2], min_pt[2]),
            )
            maximum = Gf.Vec3d(
                max(maximum[0], max_pt[0]),
                max(maximum[1], max_pt[1]),
                max(maximum[2], max_pt[2]),
            )

    if minimum is None or maximum is None:
        return Gf.Vec3d(-2.0, -2.0, 0.0), Gf.Vec3d(2.0, 2.0, 2.0)
    return minimum, maximum


def hide_high_horizontal_caps(stage: Usd.Stage) -> int:
    """Hide thin upper cover meshes so room interiors are visible in previews."""

    stage_min, stage_max = combined_stage_bounds(stage)
    stage_size = stage_max - stage_min
    z_span = max(float(stage_size[2]), 1e-6)
    xy_area = max(float(stage_size[0] * stage_size[1]), 1e-6)
    z_cutoff = float(stage_min[2] + z_span * 0.55)

    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
        useExtentsHint=True,
        ignoreVisibility=False,
    )

    hidden = 0
    shell_candidates = []
    for prim in stage.Traverse():
        if not prim.IsActive() or not prim.IsA(UsdGeom.Gprim):
            continue
        aligned = bbox_cache.ComputeWorldBound(prim).ComputeAlignedBox()
        if aligned.IsEmpty():
            continue
        prim_min = aligned.GetMin()
        prim_max = aligned.GetMax()
        size = prim_max - prim_min
        center_z = float((prim_min[2] + prim_max[2]) * 0.5)
        thin_z = float(size[2]) <= max(z_span * 0.08, 0.18)
        area_ratio = float(size[0] * size[1]) / xy_area
        broad_xy = area_ratio >= 0.12
        high = center_z >= z_cutoff
        if thin_z and broad_xy and high:
            UsdGeom.Imageable(prim).MakeInvisible()
            hidden += 1
            continue

        path = str(prim.GetPath())
        if (
            hidden == 0
            and "/part_" in path
            and area_ratio >= 0.65
            and float(prim_max[2]) >= float(stage_min[2] + z_span * 0.82)
        ):
            shell_candidates.append((float(prim_max[2]), area_ratio, prim))

    if hidden == 0 and shell_candidates:
        _max_z, _area_ratio, prim = max(shell_candidates, key=lambda item: (item[0], item[1]))
        UsdGeom.Imageable(prim).MakeInvisible()
        hidden += 1
    return hidden


def set_camera_transform(
    camera: UsdGeom.Camera,
    eye: Gf.Vec3d,
    target: Gf.Vec3d,
    up: Gf.Vec3d | None = None,
) -> None:
    if up is None:
        up = Gf.Vec3d(0.0, 0.0, 1.0)
    view = Gf.Matrix4d(1.0)
    view.SetLookAt(eye, target, up)
    transform = view.GetInverse()

    xformable = UsdGeom.Xformable(camera.GetPrim())
    xformable.ClearXformOpOrder()
    xformable.AddTransformOp().Set(transform)


def add_preview_lighting(stage: Usd.Stage, center: Gf.Vec3d, radius: float) -> None:
    dome = UsdLux.DomeLight.Define(stage, Sdf.Path("/PreviewDomeLight"))
    dome.CreateIntensityAttr(900.0)
    dome.CreateColorTemperatureAttr(6500.0)
    dome.CreateEnableColorTemperatureAttr(True)

    sun = UsdLux.DistantLight.Define(stage, Sdf.Path("/PreviewSunLight"))
    sun.CreateIntensityAttr(2800.0)
    sun.CreateAngleAttr(0.45)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-48.0, 0.0, 32.0))

    key = UsdLux.SphereLight.Define(stage, Sdf.Path("/PreviewKeyLight"))
    key.CreateRadiusAttr(max(radius * 0.18, 0.8))
    key.CreateIntensityAttr(max(radius * radius * 900.0, 7000.0))
    UsdGeom.Xformable(key.GetPrim()).AddTranslateOp().Set(
        Gf.Vec3d(center[0] - radius * 0.3, center[1] - radius * 0.7, center[2] + radius * 1.1)
    )


def add_preview_camera(stage: Usd.Stage) -> Sdf.Path:
    min_pt, max_pt = combined_stage_bounds(stage)
    center = (min_pt + max_pt) * 0.5
    size = max_pt - min_pt
    radius = max(float(size[0]), float(size[1]), float(size[2]), 1.0)

    target = Gf.Vec3d(
        center[0],
        center[1],
        min_pt[2] + max(float(size[2]) * 0.45, 0.8),
    )
    eye = Gf.Vec3d(
        center[0] + radius * 0.75,
        center[1] - radius * 1.05,
        max_pt[2] + radius * 0.55,
    )

    add_preview_lighting(stage, center, radius)

    camera_path = Sdf.Path("/PreviewCamera")
    camera = UsdGeom.Camera.Define(stage, camera_path)
    camera.CreateFocalLengthAttr(22.0)
    camera.CreateFocusDistanceAttr((eye - target).GetLength())
    camera.CreateFStopAttr(8.0)
    camera.CreateHorizontalApertureAttr(28.0)
    set_camera_transform(camera, eye, target)
    return camera_path


def open_stage(path: Path) -> Usd.Stage:
    import omni.usd

    context = omni.usd.get_context()
    opened = context.open_stage(str(path))
    wait_frames(10)
    stage = context.get_stage()
    if stage is None or opened is False:
        raise RuntimeError(f"Unable to open stage: {path}")
    return stage


def capture_scene(path: Path, output_name: str, width: int, height: int, settle_frames: int) -> Path:
    from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport

    stage = open_stage(path)
    hidden_caps = hide_high_horizontal_caps(stage)
    if hidden_caps:
        print(f"    hidden upper cap prims: {hidden_caps}", flush=True)
        wait_frames(2)
    camera_path = add_preview_camera(stage)
    wait_frames(5)

    viewport = get_active_viewport()
    if viewport is None:
        raise RuntimeError("No active viewport available for capture")

    try:
        viewport.camera_path = camera_path
    except TypeError:
        viewport.camera_path = str(camera_path)
    try:
        viewport.resolution = (width, height)
    except Exception:
        pass

    wait_frames(settle_frames)
    output_path = path.parent / output_name
    if output_path.exists():
        output_path.unlink()
    capture = capture_viewport_to_file(viewport, str(output_path), is_hdr=False)

    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        wait_frames(1)
        if output_path.exists() and output_path.stat().st_size > 0:
            break
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Viewport capture failed: {output_path}")
    wait_frames(2)
    return output_path


def run(args: argparse.Namespace) -> int:
    configure_rendering(args.width, args.height)
    scenes = [Path(item).expanduser().resolve() for item in (args.scene or DEFAULT_SCENES)]
    print(f"Rendering {len(scenes)} background scene(s)", flush=True)

    failures = 0
    for index, scene in enumerate(scenes, 1):
        if not scene.exists():
            print(f"[{index}/{len(scenes)}] missing: {scene}", flush=True)
            failures += 1
            continue
        try:
            print(f"[{index}/{len(scenes)}] loading {scene}", flush=True)
            out = capture_scene(scene, args.output_name, args.width, args.height, args.settle_frames)
            print(f"[{index}/{len(scenes)}] saved {out}", flush=True)
        except Exception as exc:
            failures += 1
            print(f"[{index}/{len(scenes)}] failed {scene}: {exc}", flush=True)

    return 1 if failures else 0


def main() -> None:
    global SIMULATION_APP

    args = parse_args(script_args())
    exit_code = 1
    try:
        SIMULATION_APP = maybe_launch_simulation_app(args)
        load_runtime_modules()
        exit_code = run(args)
    except Exception as exc:
        print(f"Fatal error: {exc}", flush=True)
        raise
    finally:
        if SIMULATION_APP is not None:
            SIMULATION_APP.close()
        elif args.quit:
            import omni.kit.app

            app = omni.kit.app.get_app()
            app.post_quit(exit_code)


main()
