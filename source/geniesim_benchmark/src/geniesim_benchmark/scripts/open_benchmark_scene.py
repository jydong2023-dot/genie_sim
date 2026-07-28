"""Importable facade for the repository scene-viewer script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "open_benchmark_scene.py"
_SPEC = importlib.util.spec_from_file_location(
    "geniesim_benchmark._open_benchmark_scene_impl", _SCRIPT
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load benchmark scene viewer implementation: {_SCRIPT}")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

for _name in dir(_MODULE):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_MODULE, _name)
