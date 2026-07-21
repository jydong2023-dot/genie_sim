import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1] / "src" / "geniesim_generator"


class OpenAIDeploymentConfigTest(unittest.TestCase):
    def test_compose_requires_runtime_key_for_text_and_webui(self):
        compose = yaml.safe_load(
            (ROOT / "compose.yaml").read_text(encoding="utf-8")
        )
        text_env = compose["services"]["mcp-server_text"]["environment"]
        webui_env = compose["services"]["open-webui"]["environment"]

        self.assertIn(
            "TEXT_EMBEDDING_API_KEY=${OPENAI_API_KEY:?set OPENAI_API_KEY}",
            text_env,
        )
        self.assertIn(
            "OPENAI_API_KEY=${OPENAI_API_KEY:?set OPENAI_API_KEY}", webui_env
        )
        self.assertIn(
            "OPENAI_API_BASE_URL=https://api.openai.com/v1", webui_env
        )

    def test_exports_target_openai_without_embedding_a_secret(self):
        workspace = json.loads(
            (ROOT / "config" / "openwebui.json").read_text(encoding="utf-8")
        )
        model = json.loads(
            (ROOT / "config" / "geniesimscenegen.json").read_text(
                encoding="utf-8"
            )
        )[0]

        self.assertEqual(
            workspace["openai"]["api_base_urls"],
            ["https://api.openai.com/v1"],
        )
        self.assertEqual(model["base_model_id"], "gpt-5.6-sol")
        self.assertNotIn("sk-", json.dumps(workspace))


if __name__ == "__main__":
    unittest.main()
