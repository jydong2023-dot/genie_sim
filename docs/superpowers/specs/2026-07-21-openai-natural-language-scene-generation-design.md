# OpenAI Natural-Language Scene Generation Design

## Goal

Enable the existing GenieSim Open WebUI workflow to accept a natural-language
scene description, retrieve real assets, emit `LLM_RESULT.py`, and compile a
benchmark scene bundle without using the currently saturated GPU.

## Selected Approach

Use the existing Docker Compose `text` profile with OpenAI for both remote
model roles:

- `gpt-5.6-sol` generates Scene Language DSL through the
  `geniesimscenegen` Open WebUI model.
- `text-embedding-3-small` with 1024 dimensions builds and queries the asset
  vector index.

Alternatives considered:

- The local `vl` profile provides image-aware retrieval, but cannot start while
  the RTX 4090 has almost all VRAM allocated.
- The default DashScope text profile avoids source changes but requires a
  separate credential that is not available in the supplied key file.

## Credential Handling

`openai_key.yaml` remains a local, untracked scalar secret. Runtime commands
load it into `OPENAI_API_KEY`; the key must not be copied into tracked JSON,
Compose YAML, logs, generated scenes, or documentation.

The MCP text backend receives its non-secret endpoint/model/dimension from its
configuration and its key from the environment. Open WebUI receives the same
environment credential and the standard OpenAI API base URL.

## Runtime Flow

1. Resolve `GENIESIM_ASSETS_DIR` from the installed `geniesim_assets` package.
2. Start the Compose `text` profile and Open WebUI.
3. On the first run, embed the 1,245-asset catalog and persist the ChromaDB
   cache under `server_chromadb/`.
4. Expose `search_assets`, `get_interactions`, and `save_file` through the MCP
   gateway on port 8765.
5. Import or configure the GenieSim model and tool exports in Open WebUI, using
   `gpt-5.6-sol` as the base model.
6. Submit a small tabletop prompt, confirm that `LLM_RESULT.py` is written, run
   `app.py`, and validate the five expected scene artifacts under the benchmark
   `llm_task` directory.

## Failure Handling

- Stop before startup if the key is missing or empty.
- Do not print API responses that may contain authorization headers.
- Treat embedding failures, MCP route failures, and DSL compilation failures as
  separate layers and report the failing layer explicitly.
- Preserve the current `LLM_RESULT.py` before allowing the WebUI file tool to
  replace it.
- Do not free or terminate unrelated GPU workloads; this design avoids them.

## Verification

- OpenAI model listing contains `gpt-5.6-sol`.
- A 1024-dimensional `text-embedding-3-small` request succeeds.
- Compose reports the text MCP service and Open WebUI running.
- All three MCP OpenAPI routes are registered on port 8765.
- Open WebUI lists the selected OpenAI model and can call the GenieSim tools.
- A natural-language smoke prompt produces a compilable `LLM_RESULT.py` and a
  scene bundle containing `scene.usda`, `scene_info.json`, `graph.dot`,
  `graph.svg`, and the DSL source snapshot.
