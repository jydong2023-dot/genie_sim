# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

import json
import os
from pathlib import Path
from typing import Any


def load_text_embedding_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        config = json.load(stream)

    api_key = os.getenv("TEXT_EMBEDDING_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "TEXT_EMBEDDING_API_KEY is required for text embedding mode"
        )

    config["api_key"] = api_key
    return config
