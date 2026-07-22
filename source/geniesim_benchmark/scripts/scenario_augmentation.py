#!/usr/bin/env python3
"""Compatibility re-export for the standalone :mod:`scene_augmentation` package."""

from __future__ import annotations

import sys
from pathlib import Path


_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_STANDALONE_SRC = _SOURCE_ROOT / "scene_augmentation" / "src"
if _STANDALONE_SRC.is_dir() and str(_STANDALONE_SRC) not in sys.path:
    sys.path.insert(0, str(_STANDALONE_SRC))

from scene_augmentation.scenario_augmentation import *  # noqa: F401,F403,E402
