#!/usr/bin/env python3
"""Stitch recording_data head_color.mp4 clips into 2x2 grid videos (4 clips each)."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

CLIPS_PER_GRID = 4
COLS = 2
ROWS = 2


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def find_videos(recording_root: Path) -> list[Path]:
    return sorted(recording_root.glob("*/observations/videos/head_color.mp4"))


def folder_task_stem(folder_name: str) -> str:
    name = folder_name.strip("[]")
    return re.sub(r"\d+$", "", name).rstrip("_")


def load_saved_task_english(stem: str) -> str:
    saved = repo_root() / "saved_task" / "first_run_demos" / stem
    candidates: list[Path] = []
    if saved.is_dir():
        candidates = sorted(saved.glob("*.json"))
    else:
        candidates = sorted((repo_root() / "saved_task").rglob(f"{stem}_*.json"))

    for json_path in candidates:
        en = _english_from_json(json_path)
        if en:
            return en
    return ""


def _english_from_json(json_path: Path) -> str:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    desc = data.get("task_description", {})
    return str(desc.get("english_task_name") or "")


def load_task_labels(video_path: Path) -> tuple[str, str]:
    task_dir = video_path.parents[2]
    folder_name = task_dir.name
    en = ""

    data_info = task_dir / "data_info.json"
    if data_info.is_file():
        try:
            info = json.loads(data_info.read_text(encoding="utf-8"))
            en = info.get("english_task_name") or ""
            if not en:
                actions = info.get("label_info", {}).get("action_config", [])
                if actions:
                    en = " | ".join(
                        a.get("english_action_text", "")
                        for a in actions
                        if a.get("english_action_text")
                    )
        except (OSError, json.JSONDecodeError):
            pass

    if not en:
        en = load_saved_task_english(folder_task_stem(folder_name))

    if not en:
        en = folder_task_stem(folder_name).replace("_", " ")

    return folder_name, en


def probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    return float(subprocess.check_output(cmd, text=True).strip())


def probe_size(path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        str(path),
    ]
    w, h = subprocess.check_output(cmd, text=True).strip().split(",")
    return int(w), int(h)


def escape_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "\\%")
    return text


def build_label_filter(folder_name: str, en: str) -> str:
    lines = [folder_name, en]
    filters = []
    y_base = 8
    line_h = 22
    for i, line in enumerate(lines):
        if not line:
            continue
        txt = escape_drawtext(line)
        y = y_base + i * line_h
        filters.append(
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
            f"text='{txt}':x=8:y={y}:fontsize=16:fontcolor=white:"
            f"box=1:boxcolor=black@0.55:boxborderw=6"
        )
    return ",".join(filters)


def render_labeled_cell(
    src: Path | None,
    dst: Path,
    folder_name: str,
    en: str,
    duration: float,
    width: int,
    height: int,
    label_h: int,
) -> None:
    out_h = height + label_h
    if src is None:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:d={duration:.3f}",
            "-vf",
            f"pad={width}:{out_h}:0:{label_h}:black,{build_label_filter(folder_name, en)}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-an",
            str(dst),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    vf = (
        f"scale={width}:{height},"
        f"pad={width}:{out_h}:0:{label_h}:black,"
        f"{build_label_filter(folder_name, en)}"
    )
    src_duration = probe_duration(src)
    pad = max(0.0, duration - src_duration)
    if pad > 0:
        vf += f",tpad=stop_mode=clone:stop_duration={pad:.3f}"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-an",
        str(dst),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def hstack_row(left: Path, right: Path, dst: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(left),
        "-i",
        str(right),
        "-filter_complex",
        "[0:v][1:v]hstack=inputs=2[v]",
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-an",
        str(dst),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def vstack_rows(rows: list[Path], dst: Path) -> None:
    inputs = []
    for row in rows:
        inputs.extend(["-i", str(row)])
    parts = "".join(f"[{i}:v]" for i in range(len(rows)))
    filt = f"{parts}vstack=inputs={len(rows)}[v]"
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filt,
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-an",
        str(dst),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_grid_2x2(
    batch: list[tuple[Path | None, str, str]],
    output_path: Path,
    tmp_dir: Path,
    batch_idx: int,
) -> None:
    real_videos = [v for v, _, _ in batch if v is not None]
    if not real_videos:
        return

    width, height = probe_size(real_videos[0])
    label_h = 50
    batch_max = max(probe_duration(v) for v in real_videos)

    cells: list[Path] = []
    for cell_idx in range(CLIPS_PER_GRID):
        if cell_idx < len(batch):
            video, folder_name, en = batch[cell_idx]
        else:
            video, folder_name, en = None, "", ""

        cell_path = tmp_dir / f"batch{batch_idx}_cell{cell_idx}.mp4"
        if video is None:
            render_labeled_cell(
                None,
                cell_path,
                folder_name or "placeholder",
                en,
                batch_max,
                width,
                height,
                label_h,
            )
        else:
            render_labeled_cell(
                video,
                cell_path,
                folder_name,
                en,
                batch_max,
                width,
                height,
                label_h,
            )
        cells.append(cell_path)

    top_row = tmp_dir / f"batch{batch_idx}_top.mp4"
    bottom_row = tmp_dir / f"batch{batch_idx}_bottom.mp4"
    hstack_row(cells[0], cells[1], top_row)
    hstack_row(cells[2], cells[3], bottom_row)
    vstack_rows([top_row, bottom_row], output_path)


def main() -> None:
    recording_root = repo_root() / "recording_data"
    videos = find_videos(recording_root)
    if not videos:
        raise SystemExit(f"No head_color.mp4 found under {recording_root}")

    entries: list[tuple[Path, str, str]] = []
    for video in videos:
        folder_name, en = load_task_labels(video)
        entries.append((video, folder_name, en))

    outputs: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="head_color_grid_") as tmp:
        tmp_dir = Path(tmp)
        for batch_idx in range(0, len(entries), CLIPS_PER_GRID):
            batch_entries = entries[batch_idx : batch_idx + CLIPS_PER_GRID]
            batch: list[tuple[Path | None, str, str]] = [
                (video, folder_name, en) for video, folder_name, en in batch_entries
            ]
            while len(batch) < CLIPS_PER_GRID:
                batch.append((None, "", ""))

            output_path = recording_root / f"recording_grid_head_color_{batch_idx // CLIPS_PER_GRID + 1:02d}.mp4"
            build_grid_2x2(batch, output_path, tmp_dir, batch_idx // CLIPS_PER_GRID)
            outputs.append(output_path)

    old_output = recording_root / "recording_grid_head_color.mp4"
    if old_output.exists():
        old_output.unlink()

    for path in outputs:
        print(f"Wrote {path}")
    print(f"Clips: {len(entries)} -> {len(outputs)} grid video(s), 2x2 each (English labels only)")


if __name__ == "__main__":
    main()
