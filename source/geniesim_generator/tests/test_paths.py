# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from geniesim_generator.paths import (
    ASSETS_DIR_ENV,
    OUTPUT_DIR_ENV,
    resolve_asset_path,
    resolve_assets_root,
    resolve_generator_output_root,
)


class PathResolutionTests(unittest.TestCase):
    def _package(self, root: Path, name: str) -> Path:
        package = root / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        return package

    def _spec(self, package: Path):
        return SimpleNamespace(
            origin=str(package / "__init__.py"),
            submodule_search_locations=[str(package)],
        )

    def test_assets_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = self._package(Path(tmp), "custom_assets")
            with patch.dict(os.environ, {ASSETS_DIR_ENV: str(assets)}, clear=True):
                with patch("geniesim_generator.paths.find_spec") as find_spec:
                    self.assertEqual(resolve_assets_root(), assets.resolve())
                    find_spec.assert_not_called()

    def test_assets_fall_back_to_installed_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = self._package(Path(tmp), "geniesim_assets")
            with patch.dict(os.environ, {}, clear=True):
                with patch("geniesim_generator.paths.find_spec", return_value=self._spec(assets)):
                    self.assertEqual(resolve_assets_root(), assets.resolve())

    def test_invalid_assets_override_fails(self):
        missing = Path("/definitely/missing/geniesim-assets")
        with patch.dict(os.environ, {ASSETS_DIR_ENV: str(missing)}, clear=True):
            with self.assertRaisesRegex(RuntimeError, ASSETS_DIR_ENV):
                resolve_assets_root()

    def test_output_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "llm_task"
            output.mkdir()
            with patch.dict(os.environ, {OUTPUT_DIR_ENV: str(output)}, clear=True):
                with patch("geniesim_generator.paths.find_spec") as find_spec:
                    self.assertEqual(resolve_generator_output_root(), output.resolve())
                    find_spec.assert_not_called()

    def test_invalid_output_override_fails(self):
        missing = Path("/definitely/missing/llm-task")
        with patch.dict(os.environ, {OUTPUT_DIR_ENV: str(missing)}, clear=True):
            with self.assertRaisesRegex(RuntimeError, OUTPUT_DIR_ENV):
                resolve_generator_output_root()

    def test_output_falls_back_to_importable_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = self._package(Path(tmp), "geniesim_benchmark")
            output = package / "benchmark" / "config" / "llm_task"
            output.mkdir(parents=True)
            with patch.dict(os.environ, {}, clear=True):
                with patch("geniesim_generator.paths.find_spec", return_value=self._spec(package)):
                    self.assertEqual(resolve_generator_output_root(), output.resolve())

    def test_output_falls_back_to_sibling_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "repo" / "source"
            module = source / "geniesim_generator" / "src" / "geniesim_generator" / "paths.py"
            module.parent.mkdir(parents=True)
            output = (
                source
                / "geniesim_benchmark"
                / "src"
                / "geniesim_benchmark"
                / "benchmark"
                / "config"
                / "llm_task"
            )
            output.mkdir(parents=True)
            with patch.dict(os.environ, {}, clear=True):
                with patch("geniesim_generator.paths.find_spec", return_value=None):
                    with patch("geniesim_generator.paths.__file__", str(module)):
                        self.assertEqual(resolve_generator_output_root(), output.resolve())

    def test_missing_output_root_explains_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "repo" / "source" / "geniesim_generator" / "src" / "geniesim_generator" / "paths.py"
            module.parent.mkdir(parents=True)
            with patch.dict(os.environ, {}, clear=True):
                with patch("geniesim_generator.paths.find_spec", return_value=None):
                    with patch("geniesim_generator.paths.__file__", str(module)):
                        with self.assertRaisesRegex(RuntimeError, OUTPUT_DIR_ENV):
                            resolve_generator_output_root()

    def test_resolve_asset_path_rejects_missing_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = self._package(Path(tmp), "geniesim_assets")
            with patch.dict(os.environ, {ASSETS_DIR_ENV: str(assets)}, clear=True):
                with self.assertRaisesRegex(FileNotFoundError, "objects/missing.usda"):
                    resolve_asset_path("objects/missing.usda")


if __name__ == "__main__":
    unittest.main()
