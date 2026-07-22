"""Importable facade for the repository preview-gallery script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "preview_task_gallery.py"
_SPEC = importlib.util.spec_from_file_location(
    "geniesim_benchmark._preview_task_gallery_impl", _SCRIPT
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load preview gallery implementation: {_SCRIPT}")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

for _name in dir(_MODULE):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_MODULE, _name)


def discover_repo_root(start: Path | None = None) -> Path:
    """Facade-local variant so callers can override ``package_root`` in tests."""
    env_root = _MODULE.os.environ.get("GENIESIM_REPO_ROOT") or _MODULE.os.environ.get(
        "SIM_REPO_ROOT"
    )
    if env_root:
        return Path(env_root).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "source" / "geniesim_benchmark").is_dir() and (
            candidate / "VERSION"
        ).is_file():
            return candidate
    return package_root().parent.parent.parent.parent.resolve()
