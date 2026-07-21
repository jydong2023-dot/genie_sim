# OpenAI Scene Generation README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone Chinese README whose primary purpose is to give users copyable commands for running the natural-language GenieSim scene-generation demo.

**Architecture:** Add one focused operational document beside the generator package README. Organize it as a linear demo workflow first, followed by output inspection, service lifecycle commands, and concise troubleshooting; do not change scripts, Compose, or runtime configuration.

**Tech Stack:** Markdown, Conda, Docker Compose, Open WebUI, GenieSim generator CLI, curl, OpenUSD output files

---

### Task 1: Write the demo-first operations README

**Files:**
- Create: `source/geniesim_generator/README_OPENAI_SCENE_GENERATION.md`
- Reference: `source/geniesim_generator/src/geniesim_generator/compose.yaml`
- Reference: `source/geniesim_generator/skills/deploy-generator/SKILL.md`
- Reference: `source/geniesim_generator/skills/generate-scene/SKILL.md`

- [ ] **Step 1: Verify the documented prerequisites and current runtime values**

Run:

```bash
test -f /home/user/djy/genie_sim/source/geniesim_generator/openai_key.yaml
test -f /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator/app.py
test -d /home/user/djy/geniesim_assets
conda env list | grep '^geniesim-generator '
rg -n 'PORT=3000|8765:8765|text-embedding-3-small' \
  /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator/compose.yaml
```

Expected: all `test` commands exit 0; the Conda environment is listed; Compose shows ports 3000/8765 and the OpenAI embedding model.

- [ ] **Step 2: Create the README with a complete quick-start command sequence**

The README must open with the shortest complete demo path and contain these exact command contracts:

```bash
cd /home/user/djy/genie_sim
conda activate geniesim-generator

export OPENAI_API_KEY="$(tr -d '\r\n' < \
  /home/user/djy/genie_sim/source/geniesim_generator/openai_key.yaml)"

export GENIESIM_ASSETS_DIR="$(python -c \
  'import geniesim_assets, os; print(os.path.dirname(geniesim_assets.__file__))')"

cd /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator
BUILDX_CONFIG=/tmp/geniesim-buildx \
docker compose --profile text up -d --build
```

Then document these checks:

```bash
docker compose ps
curl -fsS http://127.0.0.1:3000/health
curl -fsS http://127.0.0.1:8765/assets-agent/openapi.json \
  | python -m json.tool
```

Explain the WebUI operation precisely:

1. Open `http://127.0.0.1:3000`.
2. Select `GenieSim Generator`.
3. Enter the supplied Chinese tabletop prompt.
4. Run `Save Code to File` on the generated response.
5. Confirm that `src/geniesim_generator/LLM_RESULT.py` changed.

Include this compilation sequence, with `scene_id` explained as a lowercase output-directory identifier rather than an asset ID:

```bash
cd /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator

export GENIESIM_GENERATOR_OUTPUT_DIR=\
/home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task

PYTHONPATH=/home/user/djy/genie_sim/source/geniesim_generator/src \
python app.py --scene_id natural_language_tabletop_demo
```

Document the expected output directory and its five generated files:

```text
source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/
└── natural_language_tabletop_demo/
    └── 0/
        ├── LLM_RESULT.py
        ├── graph.dot
        ├── graph.svg
        ├── scene.usda
        └── scene_info.json
```

Finish with exact lifecycle and diagnostic commands:

```bash
docker compose logs -f --tail=100 open-webui mcp-server_text
docker compose restart open-webui mcp-server_text
docker compose --profile text down
```

The troubleshooting section must state:

- first-run asset indexing can delay MCP readiness;
- Open WebUI uses port 3000 because port 8080 may be occupied;
- missing `OPENAI_API_KEY` or `GENIESIM_ASSETS_DIR` causes Compose to fail fast;
- the model must be `GenieSim Generator` and the save action must be active;
- scene compilation does not require Isaac Sim, while live visual preview does;
- `app.py` must run from its own package directory because it uses script-relative imports.

- [ ] **Step 3: Check Markdown content and secret hygiene**

Run:

```bash
rg -n '^#|^##|^###|```' \
  source/geniesim_generator/README_OPENAI_SCENE_GENERATION.md
rg -n 'sk-[A-Za-z0-9_-]+' \
  source/geniesim_generator/README_OPENAI_SCENE_GENERATION.md
git diff --check -- \
  source/geniesim_generator/README_OPENAI_SCENE_GENERATION.md
```

Expected: headings and fences are present; the key-pattern scan returns no matches; `git diff --check` exits 0.

- [ ] **Step 4: Validate the non-mutating demo commands against the running stack**

Run:

```bash
cd /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator
export OPENAI_API_KEY="$(tr -d '\r\n' < \
  /home/user/djy/genie_sim/source/geniesim_generator/openai_key.yaml)"
export GENIESIM_ASSETS_DIR=/home/user/djy/geniesim_assets
docker compose ps
curl -fsS http://127.0.0.1:3000/health
curl -fsS -X POST -H 'Content-Type: application/json' \
  -d '{"keyword":"transparent beverage bottle","topk":1}' \
  http://127.0.0.1:8765/assets-agent/search_assets
```

Expected: both containers are up, WebUI returns `{"status":true}`, and asset search returns at least one result.

- [ ] **Step 5: Verify the documented compiler invocation without creating a new instance**

Use Python compilation plus the already generated smoke bundle rather than rerunning `app.py`, which would intentionally create another numbered instance:

```bash
python -m py_compile \
  source/geniesim_generator/src/geniesim_generator/app.py

conda run -n geniesim-generator python -c \
  "from pxr import Usd; p='source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/openai_nl_smoke/0/scene.usda'; assert Usd.Stage.Open(p); print('USD OK')"
```

Expected: Python compilation exits 0 and the OpenUSD check prints `USD OK`.

- [ ] **Step 6: Commit only the standalone README**

```bash
git add source/geniesim_generator/README_OPENAI_SCENE_GENERATION.md
git commit -m "docs(generator): add OpenAI scene generation demo guide"
```

Expected: one new Markdown file is committed; unrelated working-tree changes remain untouched.
