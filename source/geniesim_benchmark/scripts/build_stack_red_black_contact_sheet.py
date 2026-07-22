#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

"""Build a labeled contact sheet from red-on-black benchmark previews."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


COLUMNS = 5
ROWS = 8
TILE_WIDTH = 320
TILE_HEIGHT = 220
IMAGE_WIDTH = 300
IMAGE_HEIGHT = 175
CONTACT_SHEET_SIZE = (COLUMNS * TILE_WIDTH, ROWS * TILE_HEIGHT)


def _image_path(preview_dir: Path, camera: str, instance_id: int) -> Path:
    name = f"{camera}.png" if instance_id == 0 else f"{camera}_{instance_id:02d}.png"
    return preview_dir / name


def _has_visual_content(image: Image.Image) -> bool:
    return any(low != high for low, high in image.convert("RGB").getextrema())


def build_contact_sheet(
    preview_dir: Path,
    manifest_path: Path,
    output_path: Path,
    camera: str = "head",
) -> Path:
    preview_dir = Path(preview_dir)
    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = manifest.get("scenarios", [])
    instance_ids = [scenario.get("instance_id") for scenario in scenarios]
    if instance_ids != list(range(40)):
        raise ValueError(f"Expected manifest instance IDs 0-39, got {instance_ids}")

    missing = [instance_id for instance_id in instance_ids if not _image_path(preview_dir, camera, instance_id).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing {camera} preview images for instance IDs: {missing}")

    sheet = Image.new("RGB", CONTACT_SHEET_SIZE, (242, 242, 240))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=18)
    for scenario in scenarios:
        instance_id = scenario["instance_id"]
        source_path = _image_path(preview_dir, camera, instance_id)
        with Image.open(source_path) as source:
            source = source.convert("RGB")
            if not _has_visual_content(source):
                raise ValueError(f"Preview image is blank for instance {instance_id}: {source_path}")
            thumbnail = ImageOps.contain(source, (IMAGE_WIDTH, IMAGE_HEIGHT), Image.Resampling.LANCZOS)

        column = instance_id % COLUMNS
        row = instance_id // COLUMNS
        tile_x = column * TILE_WIDTH
        tile_y = row * TILE_HEIGHT
        image_x = tile_x + (TILE_WIDTH - thumbnail.width) // 2
        image_y = tile_y + 10 + (IMAGE_HEIGHT - thumbnail.height) // 2
        sheet.paste(thumbnail, (image_x, image_y))
        draw.rectangle((tile_x, tile_y, tile_x + TILE_WIDTH - 1, tile_y + TILE_HEIGHT - 1), outline=(150, 150, 146))
        draw.text(
            (tile_x + 10, tile_y + IMAGE_HEIGHT + 18),
            f"{instance_id:02d}  {scenario['dimension']}",
            fill=(20, 20, 20),
            font=font,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--camera", default="head")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = build_contact_sheet(args.preview_dir, args.manifest, args.output, args.camera)
    print(f"Contact sheet: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
