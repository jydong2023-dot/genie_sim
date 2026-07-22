import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PACKAGE_ROOT / "src" / "geniesim_generator" / "server" / "save_to_local.py"
EXPORT_PATH = (
    PACKAGE_ROOT
    / "src"
    / "geniesim_generator"
    / "config"
    / "function-save_code_to_file.json"
)
RAW_DSL = """from helper import *

@register()
def root_scene() -> Shape:
    return []
"""


def _load_action_module():
    spec = importlib.util.spec_from_file_location("save_to_local_action", SOURCE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SaveToLocalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_action_module()

    def setUp(self):
        self.action = self.module.Action.__new__(self.module.Action)

    def test_extracts_legacy_fenced_code(self):
        messages = [
            {
                "role": "assistant",
                "content": "Here is the scene:\n```python\nprint('old format')\n```",
            }
        ]

        self.assertEqual(
            self.action._find_code_blocks(messages),
            [("python", "print('old format')")],
        )

    def test_extracts_raw_dsl_from_original_content(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "originalContent": RAW_DSL,
                "output": [],
            }
        ]

        self.assertEqual(
            self.action._find_code_blocks(messages),
            [("python", RAW_DSL.strip())],
        )

    def test_extracts_raw_dsl_from_responses_output(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "output": [
                    {"type": "function_call", "name": "search_assets"},
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": RAW_DSL}],
                    },
                ],
            }
        ]

        self.assertEqual(
            self.action._find_code_blocks(messages),
            [("python", RAW_DSL.strip())],
        )

    def test_scans_back_to_latest_assistant_code(self):
        messages = [
            {"role": "assistant", "content": "", "originalContent": RAW_DSL},
            {"role": "user", "content": "Save it"},
        ]

        self.assertEqual(
            self.action._find_code_blocks(messages),
            [("python", RAW_DSL.strip())],
        )

    def test_rejects_unfenced_non_dsl_text(self):
        messages = [
            {"role": "assistant", "content": "print('not a GenieSim scene')"}
        ]

        self.assertEqual(self.action._find_code_blocks(messages), [])

    def test_does_not_save_stale_code_past_newer_assistant_prose(self):
        messages = [
            {"role": "assistant", "content": "", "originalContent": RAW_DSL},
            {"role": "assistant", "content": "I could not generate this scene."},
        ]

        self.assertEqual(self.action._find_code_blocks(messages), [])

    def test_action_saves_responses_style_raw_dsl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            action = self.module.Action.__new__(self.module.Action)
            action.valves = self.module.Action.Valves(
                save_root_dir=temp_dir,
                file_name="LLM_RESULT.py",
                auto_confirm=True,
            )
            body = {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "",
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {"type": "output_text", "text": RAW_DSL}
                                ],
                            }
                        ],
                    }
                ]
            }

            result = asyncio.run(action.action(body))

            saved = Path(temp_dir) / "LLM_RESULT.py"
            self.assertIn("Successfully saved", result["content"])
            self.assertEqual(saved.read_text(encoding="utf-8"), RAW_DSL.strip())

    def test_open_webui_export_matches_action_source(self):
        source = SOURCE_PATH.read_text(encoding="utf-8")
        exported_entry = json.loads(EXPORT_PATH.read_text(encoding="utf-8"))[0]
        exported = exported_entry["content"]

        self.assertEqual(exported, source[source.index('"""') :])
        self.assertEqual(exported_entry["meta"]["manifest"]["version"], "0.2.0")
        self.assertEqual(
            exported_entry["meta"]["description"],
            "Save generated GenieSim Python from Open WebUI messages to a local directory.",
        )


if __name__ == "__main__":
    unittest.main()
