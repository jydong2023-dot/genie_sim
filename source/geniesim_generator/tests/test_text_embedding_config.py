import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geniesim_generator.server.text_embedding_config import load_text_embedding_config


class TextEmbeddingConfigTest(unittest.TestCase):
    def test_environment_key_overrides_json_without_mutating_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            original = {
                "api_key": "",
                "model": "text-embedding-3-small",
                "dimension": 1024,
            }
            path.write_text(json.dumps(original), encoding="utf-8")

            with patch.dict(
                os.environ,
                {"TEXT_EMBEDDING_API_KEY": "runtime-secret"},
                clear=False,
            ):
                loaded = load_text_embedding_config(path)

            self.assertEqual(loaded["api_key"], "runtime-secret")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)

    def test_missing_runtime_key_fails_before_api_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                '{"api_key":"","model":"text-embedding-3-small","dimension":1024}',
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "TEXT_EMBEDDING_API_KEY"):
                    load_text_embedding_config(path)


if __name__ == "__main__":
    unittest.main()
