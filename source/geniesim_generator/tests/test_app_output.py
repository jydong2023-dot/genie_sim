# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from pxr import Usd

from geniesim_generator.paths import ASSETS_DIR_ENV, OUTPUT_DIR_ENV


PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "geniesim_generator"
SOURCE_DIR = PACKAGE_DIR.parent
DISTRIBUTION_DIR = SOURCE_DIR.parent


class AppOutputTests(unittest.TestCase):
    def test_compiler_writes_complete_bundle_to_resolved_output(self):
        assets_spec = importlib.util.find_spec("geniesim_assets")
        self.assertIsNotNone(assets_spec)
        assets_root = Path(next(iter(assets_spec.submodule_search_locations))).resolve()
        scene_id = f"path_resolution_test_{uuid.uuid4().hex}"
        legacy_output = DISTRIBUTION_DIR / "src" / "benchmark" / "config" / "llm_task" / scene_id
        self.addCleanup(shutil.rmtree, legacy_output, True)

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            env = os.environ.copy()
            env[ASSETS_DIR_ENV] = str(assets_root)
            env[OUTPUT_DIR_ENV] = str(output_root)
            env["PYTHONPATH"] = os.pathsep.join(
                value for value in (str(SOURCE_DIR), env.get("PYTHONPATH")) if value
            )
            env["PYTHONDONTWRITEBYTECODE"] = "1"

            result = subprocess.run(
                [sys.executable, "app.py", "--scene_id", scene_id],
                cwd=PACKAGE_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            scene_root = output_root / scene_id
            self.assertTrue(scene_root.is_dir(), f"resolved output was not created: {scene_root}")
            instances = [path for path in scene_root.iterdir() if path.is_dir()]
            self.assertEqual(len(instances), 1)
            instance = instances[0]
            self.assertEqual(
                {path.name for path in instance.iterdir() if path.is_file()},
                {"LLM_RESULT.py", "graph.dot", "graph.svg", "scene.usda", "scene_info.json"},
            )

            scene_path = instance / "scene.usda"
            stage = Usd.Stage.Open(str(scene_path))
            self.assertIsNotNone(stage)
            object_prims = list(stage.GetPrimAtPath("/World/Objects").GetChildren())
            self.assertGreater(len(object_prims), 0)
            for prim in object_prims:
                prim_spec = stage.GetRootLayer().GetPrimAtPath(prim.GetPath())
                payloads = prim_spec.payloadList.prependedItems
                self.assertGreater(len(payloads), 0)
                for payload in payloads:
                    resolved = (scene_path.parent / payload.assetPath).resolve()
                    self.assertTrue(resolved.is_file(), resolved)
                self.assertGreater(len(list(Usd.PrimRange(prim))), 1)


if __name__ == "__main__":
    unittest.main()
