# OpenAI Natural-Language Scene Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run GenieSim's natural-language scene generator with OpenAI chat and text embeddings while keeping the API key out of tracked files.

**Architecture:** A small configuration loader overlays `TEXT_EMBEDDING_API_KEY` on the checked-in non-secret embedding JSON before constructing `AssetVectorDB`. Docker Compose maps the current shell's `OPENAI_API_KEY` into that variable for MCP and passes the same credential to Open WebUI; exported Open WebUI artifacts point at OpenAI and `gpt-5.6-sol`.

**Tech Stack:** Python 3.11, unittest, OpenAI Python SDK, Docker Compose, FastMCP/mcpo, Open WebUI, ChromaDB.

---

### Task 1: Environment-backed text embedding configuration

**Files:**
- Create: `source/geniesim_generator/src/geniesim_generator/server/text_embedding_config.py`
- Create: `source/geniesim_generator/tests/test_text_embedding_config.py`
- Modify: `source/geniesim_generator/src/geniesim_generator/server/mcp_assets_server.py`
- Modify: `source/geniesim_generator/src/geniesim_generator/server/mcp_text_embedding/text_embedding_config.json`

- [ ] **Step 1: Write failing configuration-loader tests**

```python
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
            original = {"api_key": "", "model": "text-embedding-3-small", "dimension": 1024}
            path.write_text(json.dumps(original), encoding="utf-8")
            with patch.dict(os.environ, {"TEXT_EMBEDDING_API_KEY": "runtime-secret"}, clear=False):
                loaded = load_text_embedding_config(path)
            self.assertEqual(loaded["api_key"], "runtime-secret")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)

    def test_missing_runtime_key_fails_before_api_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"api_key":"","model":"text-embedding-3-small","dimension":1024}', encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "TEXT_EMBEDDING_API_KEY"):
                    load_text_embedding_config(path)
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
conda run -n geniesim-generator python -m unittest tests.test_text_embedding_config -v
```

Expected: import failure because `geniesim_generator.server.text_embedding_config` does not exist.

- [ ] **Step 3: Implement the minimal loader**

```python
import json
import os
from pathlib import Path
from typing import Any


def load_text_embedding_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        config = json.load(stream)
    api_key = os.getenv("TEXT_EMBEDDING_API_KEY", "").strip()
    if not api_key:
        raise ValueError("TEXT_EMBEDDING_API_KEY is required for text embedding mode")
    config["api_key"] = api_key
    return config
```

Replace the inline `json.load(...)` in `mcp_assets_server.py` with:

```python
from geniesim_generator.server.text_embedding_config import load_text_embedding_config

config = load_text_embedding_config(
    f"{CURRENT_DIRECTORY}/mcp_text_embedding/text_embedding_config.json"
)
```

Set the checked-in JSON to:

```json
{
  "api_key": "",
  "base_url": "https://api.openai.com/v1",
  "dashscope_mode": false,
  "dimension": 1024,
  "model": "text-embedding-3-small"
}
```

- [ ] **Step 4: Run focused and full generator tests**

Run:

```bash
conda run -n geniesim-generator python -m unittest tests.test_text_embedding_config -v
conda run -n geniesim-generator python -m unittest discover -s tests -v
```

Expected: the two focused tests and all existing generator tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add source/geniesim_generator/src/geniesim_generator/server/text_embedding_config.py \
  source/geniesim_generator/src/geniesim_generator/server/mcp_assets_server.py \
  source/geniesim_generator/src/geniesim_generator/server/mcp_text_embedding/text_embedding_config.json \
  source/geniesim_generator/tests/test_text_embedding_config.py
git commit -m "feat(generator): load embedding credentials from environment"
```

### Task 2: OpenAI Compose and Open WebUI exports

**Files:**
- Create: `source/geniesim_generator/tests/test_openai_deployment_config.py`
- Modify: `source/geniesim_generator/src/geniesim_generator/compose.yaml`
- Modify: `source/geniesim_generator/src/geniesim_generator/config/openwebui.json`
- Modify: `source/geniesim_generator/src/geniesim_generator/config/geniesimscenegen.json`
- Modify: `source/geniesim_generator/AGENTS.md`
- Modify: `source/geniesim_generator/skills/deploy-generator/SKILL.md`

- [ ] **Step 1: Write failing deployment-contract tests**

```python
import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1] / "src" / "geniesim_generator"


class OpenAIDeploymentConfigTest(unittest.TestCase):
    def test_compose_requires_runtime_key_for_text_and_webui(self):
        compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        text_env = compose["services"]["mcp-server_text"]["environment"]
        webui_env = compose["services"]["open-webui"]["environment"]
        self.assertIn("TEXT_EMBEDDING_API_KEY=${OPENAI_API_KEY:?set OPENAI_API_KEY}", text_env)
        self.assertIn("OPENAI_API_KEY=${OPENAI_API_KEY:?set OPENAI_API_KEY}", webui_env)
        self.assertIn("OPENAI_API_BASE_URL=https://api.openai.com/v1", webui_env)

    def test_exports_target_openai(self):
        workspace = json.loads((ROOT / "config" / "openwebui.json").read_text(encoding="utf-8"))
        model = json.loads((ROOT / "config" / "geniesimscenegen.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(workspace["openai"]["api_base_urls"], ["https://api.openai.com/v1"])
        self.assertEqual(model["base_model_id"], "gpt-5.6-sol")
        self.assertNotIn("sk-", json.dumps(workspace))
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
conda run -n geniesim-generator python -m unittest tests.test_openai_deployment_config -v
```

Expected: assertions fail because Compose does not pass the credential and exports still target DashScope/Gemini.

- [ ] **Step 3: Update the non-secret deployment configuration**

Add to `mcp-server_text.environment`:

```yaml
- TEXT_EMBEDDING_API_KEY=${OPENAI_API_KEY:?set OPENAI_API_KEY}
```

Add to `open-webui.environment`:

```yaml
- OPENAI_API_KEY=${OPENAI_API_KEY:?set OPENAI_API_KEY}
- OPENAI_API_BASE_URL=https://api.openai.com/v1
```

Change `openwebui.json`'s API base URL to `https://api.openai.com/v1`, retain
the placeholder key, and change `geniesimscenegen.json`'s `base_model_id` to
`gpt-5.6-sol`. Update the deployment documentation to state that
`OPENAI_API_KEY` is required by the OpenAI text profile and must be loaded from
an untracked secret source.

- [ ] **Step 4: Run deployment and full tests**

Run:

```bash
conda run -n geniesim-generator python -m unittest tests.test_openai_deployment_config -v
conda run -n geniesim-generator python -m unittest discover -s tests -v
```

Expected: deployment-contract tests and all generator tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add source/geniesim_generator/src/geniesim_generator/compose.yaml \
  source/geniesim_generator/src/geniesim_generator/config/openwebui.json \
  source/geniesim_generator/src/geniesim_generator/config/geniesimscenegen.json \
  source/geniesim_generator/AGENTS.md \
  source/geniesim_generator/skills/deploy-generator/SKILL.md \
  source/geniesim_generator/tests/test_openai_deployment_config.py
git commit -m "feat(generator): configure OpenAI scene generation stack"
```

### Task 3: Start and verify the current-session stack

**Files:**
- Runtime state only: `source/geniesim_generator/src/geniesim_generator/server_chromadb/`
- Runtime state only: `source/geniesim_generator/src/geniesim_generator/server_open-webui/`
- Preserve: `source/geniesim_generator/src/geniesim_generator/LLM_RESULT.py`

Run every Task 3 command from
`source/geniesim_generator/src/geniesim_generator/` unless the step says
otherwise.

- [ ] **Step 1: Load the scalar key without printing it and resolve assets**

Run in one shell session:

```bash
export OPENAI_API_KEY="$(conda run -n geniesim-generator python -c \
  "import pathlib,yaml; print(yaml.safe_load(pathlib.Path('../../openai_key.yaml').read_text()).strip())")"
export GENIESIM_ASSETS_DIR="$(conda run -n geniesim-generator python -c \
  "import geniesim_assets,os; print(os.path.dirname(geniesim_assets.__file__))" | tail -1)"
test -n "$OPENAI_API_KEY"
test -d "$GENIESIM_ASSETS_DIR"
```

Expected: both checks exit 0 and neither secret nor authorization header is printed.

- [ ] **Step 2: Start the text profile in detached mode**

Run:

```bash
docker compose --profile text up --build -d
```

Expected: `assets-retrieval-agent_text` and `open-webui` are created. The first
asset-index build can take several minutes and incur OpenAI embedding usage.

- [ ] **Step 3: Wait for index completion and verify services**

Run:

```bash
docker compose --profile text ps
docker compose --profile text logs mcp-server_text
curl -fsS http://127.0.0.1:8765/assets-agent/openapi.json
curl -fsS http://127.0.0.1:8765/assets-info-agent/openapi.json
curl -fsS http://127.0.0.1:8765/file-agent/openapi.json
curl -fsS http://127.0.0.1:8080/health
```

Expected: both containers are running, all MCP route documents contain non-empty
`paths`, and Open WebUI health responds successfully. If the WebUI image exposes
a different host port, obtain it from its startup logs and use that port.

- [ ] **Step 4: Configure/import the exported workspace and model**

Use Open WebUI at its reported host URL. Import
`config/openwebui.json`, `config/geniesimscenegen.json`, and
`config/function-save_code_to_file.json`; verify the GenieSim Generator model
uses `gpt-5.6-sol` and has the three localhost MCP tool connections enabled.

- [ ] **Step 5: Back up the live DSL slot and submit a smoke prompt**

Run:

```bash
cp -a src/geniesim_generator/LLM_RESULT.py /tmp/LLM_RESULT.py.before-openai-scene-smoke
```

Submit this prompt to the `GenieSim Generator` model:

```text
生成一个简单桌面场景：一张桌子上放一个饮料瓶和一个碗，两件物体之间留出明显间距，物体都不能悬空或超出桌面。
```

Expected: the model searches real assets and the save action replaces the live
`LLM_RESULT.py` with a program containing exactly one registered `root_scene()`.

- [ ] **Step 6: Compile and validate the generated scene**

Run:

```bash
conda run -n geniesim-generator python app.py --scene_id openai_nl_smoke
```

Expected: a new numbered instance under
`source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/openai_nl_smoke/`
contains `scene.usda`, `scene_info.json`, `graph.dot`, `graph.svg`, and
`LLM_RESULT.py`; OpenUSD opens the scene without unresolved payload warnings.

- [ ] **Step 7: Final secret and service checks**

Run:

```bash
git status --short
git diff --check
rg -n "sk-[A-Za-z0-9_-]+" source/geniesim_generator --glob '!openai_key.yaml'
docker compose --profile text ps
```

Expected: no key appears outside `openai_key.yaml`, source diffs are clean, and
the two runtime containers remain available for the user.
