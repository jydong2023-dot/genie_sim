# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

from __future__ import annotations

import cv2
import numpy as np


def _text_width(text: str, font: int, scale: float, thickness: int) -> int:
    return cv2.getTextSize(text, font, scale, thickness)[0][0]


def _ellipsize(text: str, max_width: int, font: int, scale: float, thickness: int) -> str:
    suffix = "..."
    if _text_width(text, font, scale, thickness) <= max_width:
        return text
    while text and _text_width(text + suffix, font, scale, thickness) > max_width:
        text = text[:-1]
    return (text.rstrip() + suffix) if text else suffix


def _wrap_text(text: str, max_width: int, font: int, scale: float, thickness: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if not current or _text_width(candidate, font, scale, thickness) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def annotate_instruction(image_rgb: np.ndarray, instruction: str) -> np.ndarray:
    """Return an RGB image with a readable instruction label at the bottom."""
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError(f"image_rgb must be HxWx3, got {image_rgb.shape}")

    annotated = image_rgb.copy()
    height, width = annotated.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.7, min(1.4, width / 900.0))
    thickness = 2 if font_scale < 1.0 else 3
    margin = max(8, int(width * 0.015))
    max_width = max(20, width - 2 * margin)

    text = f"Instruction: {(instruction or '<empty>').strip()}"
    all_lines = _wrap_text(text, max_width, font, font_scale, thickness)
    max_lines = max(1, min(4, height // 24))
    lines = all_lines[:max_lines]
    if len(all_lines) > max_lines:
        lines[-1] = _ellipsize(lines[-1], max_width, font, font_scale, thickness)

    text_size = cv2.getTextSize("Ag", font, font_scale, thickness)[0]
    line_height = text_size[1] + max(6, int(text_size[1] * 0.45))
    panel_height = min(height, margin * 2 + line_height * len(lines))
    panel_top = height - panel_height

    roi = annotated[panel_top:height]
    panel = roi.copy()
    cv2.rectangle(panel, (0, 0), (width, panel_height), (0, 0, 0), -1)
    annotated[panel_top:height] = cv2.addWeighted(panel, 0.68, roi, 0.32, 0)

    y = panel_top + margin + text_size[1]
    for line in lines:
        cv2.putText(
            annotated,
            line,
            (margin, y),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            lineType=cv2.LINE_AA,
        )
        y += line_height

    return annotated
