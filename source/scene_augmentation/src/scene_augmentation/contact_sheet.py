"""Preview-image composition independent of any simulator runtime."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PIL import Image, ImageDraw


DEFAULT_CAMERAS = ("head", "left_hand", "right_hand")


def build_contact_sheet(
    preview_dir: Path,
    instance_ids: Iterable[int],
    output_path: Path | None = None,
    cameras: Iterable[str] = DEFAULT_CAMERAS,
) -> Path:
    """Combine every saved per-instance camera preview into one labeled image."""
    preview_dir = Path(preview_dir)
    ids = tuple(sorted(int(value) for value in instance_ids))
    camera_names = tuple(str(value) for value in cameras)
    if not ids:
        raise ValueError("contact sheet requires at least one instance ID")
    if not camera_names:
        raise ValueError("contact sheet requires at least one camera")
    paths = {
        (instance_id, camera): preview_dir / str(instance_id) / f"{camera}.png"
        for instance_id in ids
        for camera in camera_names
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "missing preview images for contact sheet: " + ", ".join(missing)
        )

    with Image.open(next(iter(paths.values()))) as sample:
        cell_width, cell_height = sample.size
    label_height = 30
    sheet = Image.new(
        "RGB",
        (cell_width * len(camera_names), (cell_height + label_height) * len(ids)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for row, instance_id in enumerate(ids):
        for column, camera in enumerate(camera_names):
            with Image.open(paths[(instance_id, camera)]) as source:
                image = source.convert("RGB")
                if image.size != (cell_width, cell_height):
                    image = image.resize((cell_width, cell_height))
                x = column * cell_width
                y = row * (cell_height + label_height) + label_height
                sheet.paste(image, (x, y))
                draw.text(
                    (x + 8, y - label_height + 7),
                    f"instance {instance_id} · {camera}",
                    fill="black",
                )
    output_path = Path(output_path) if output_path else preview_dir / "contact_sheet.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path
