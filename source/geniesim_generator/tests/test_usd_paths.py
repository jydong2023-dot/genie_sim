# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pxr import Usd

from geniesim_generator.paths import ASSETS_DIR_ENV
from geniesim_generator.utils.usd import gen_scene_usda


class UsdAssetPathTests(unittest.TestCase):
    def _assets_root(self, root: Path) -> tuple[Path, Path]:
        assets = root / "geniesim_assets"
        assets.mkdir()
        (assets / "__init__.py").write_text("", encoding="utf-8")
        payload = assets / "objects" / "test_asset" / "Aligned.usda"
        payload.parent.mkdir(parents=True)
        payload.write_text(
            """#usda 1.0
(
    defaultPrim = "Asset"
)

def Xform "Asset"
{
    def Xform "Visual"
    {
    }
}
""",
            encoding="utf-8",
        )
        return assets, payload

    def _object_info(self, url: str) -> dict:
        return {
            "id": "test_asset",
            "url": url,
            "type": "test",
            "translation": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0],
        }

    def test_generated_payload_resolves_and_composes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets, payload_file = self._assets_root(root)
            scene_path = root / "output" / "scene.usda"
            scene_path.parent.mkdir()

            with patch.dict(os.environ, {ASSETS_DIR_ENV: str(assets)}, clear=True):
                gen_scene_usda(
                    str(scene_path),
                    [self._object_info("objects/test_asset/Aligned.usda")],
                )

            stage = Usd.Stage.Open(str(scene_path))
            prim = stage.GetPrimAtPath("/World/Objects/test_asset")
            prim_spec = stage.GetRootLayer().GetPrimAtPath(prim.GetPath())
            authored_payload = prim_spec.payloadList.prependedItems[0]
            resolved_payload = (scene_path.parent / authored_payload.assetPath).resolve()

            self.assertEqual(resolved_payload, payload_file.resolve())
            self.assertTrue(resolved_payload.is_file())
            self.assertTrue(stage.GetPrimAtPath("/World/Objects/test_asset/Visual").IsValid())

    def test_missing_payload_fails_before_scene_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets, _ = self._assets_root(root)
            scene_path = root / "output" / "scene.usda"
            scene_path.parent.mkdir()

            with patch.dict(os.environ, {ASSETS_DIR_ENV: str(assets)}, clear=True):
                with self.assertRaisesRegex(FileNotFoundError, "objects/missing/Aligned.usda"):
                    gen_scene_usda(
                        str(scene_path),
                        [self._object_info("objects/missing/Aligned.usda")],
                    )

            self.assertFalse(scene_path.exists())


if __name__ == "__main__":
    unittest.main()
