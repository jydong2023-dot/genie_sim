#!/usr/bin/env python3
"""Synchronize the Open WebUI Save Code action export with its source."""

from __future__ import annotations

import json
import re
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ACTION_SOURCE = PACKAGE_ROOT / "src" / "geniesim_generator" / "server" / "save_to_local.py"
ACTION_EXPORT = (
    PACKAGE_ROOT
    / "src"
    / "geniesim_generator"
    / "config"
    / "function-save_code_to_file.json"
)


def main() -> int:
    source = ACTION_SOURCE.read_text(encoding="utf-8")
    exported_action = source[source.index('"""') :]
    payload = json.loads(ACTION_EXPORT.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 1:
        raise ValueError(f"Expected one exported action in {ACTION_EXPORT}")

    payload[0]["content"] = exported_action
    manifest = payload[0].setdefault("meta", {}).setdefault("manifest", {})
    for key in (
        "title",
        "author",
        "version",
        "required_open_webui_version",
        "description",
    ):
        match = re.search(rf"^{key}:\s*(.+)$", exported_action, re.MULTILINE)
        if not match:
            raise ValueError(f"Missing {key!r} metadata in {ACTION_SOURCE}")
        manifest[key] = match.group(1).strip().strip('"')
    payload[0]["meta"]["description"] = manifest["description"]
    ACTION_EXPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Synchronized {ACTION_EXPORT} from {ACTION_SOURCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
