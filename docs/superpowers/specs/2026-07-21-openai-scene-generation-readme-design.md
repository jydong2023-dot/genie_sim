# OpenAI Scene Generation README Design

## Goal

Add a standalone Chinese operations guide for generating GenieSim scenes from
natural-language prompts through the currently configured OpenAI and Open WebUI
stack.

## Location

Create:

`source/geniesim_generator/README_OPENAI_SCENE_GENERATION.md`

Keep the guide separate from the package's general `README.md` so that the
end-to-end operational workflow remains easy to find and update.

## Audience

The reader has the repository at `/home/user/djy/genie_sim`, a Conda environment
named `geniesim-generator`, the local asset package, Docker, and an untracked
OpenAI key file at `source/geniesim_generator/openai_key.yaml`.

## Structure

The README will use a quick-start-first layout:

1. Prerequisites and fixed paths.
2. Activate the Conda environment and load the API key without printing it.
3. Resolve `GENIESIM_ASSETS_DIR` and start the text MCP/Open WebUI stack.
4. Verify ports 3000 and 8765 and inspect container status.
5. Open WebUI, select `GenieSim Generator`, enter a natural-language prompt,
   and invoke `Save Code to File`.
6. Compile the saved `LLM_RESULT.py` with `app.py --scene_id`.
7. Locate and inspect `scene.usda`, `scene_info.json`, `graph.svg`, and the saved
   generator program.
8. Restart, inspect logs, and stop services.
9. Troubleshoot the known port, environment, path, indexing, model-tool, and
   preview constraints.

## Command Contract

- Commands use the current absolute repository path to reduce ambiguity.
- Open WebUI is documented at `http://127.0.0.1:3000` and MCP at port 8765.
- The text profile uses OpenAI `text-embedding-3-small` and does not require a
  GPU.
- API key loading reads the untracked YAML file into an environment variable;
  no command echoes the secret and no secret value appears in the README.
- Compilation runs from `src/geniesim_generator` because `app.py` relies on
  script-relative imports.
- `scene_id` is described as the output directory identifier, with a safe
  lowercase underscore example.
- The output override points to the sibling benchmark package's `llm_task`
  directory.

## Error Handling

The troubleshooting section will distinguish:

- service startup/indexing delay from a failed container;
- host port 8080 conflicts from the configured port 3000;
- missing runtime environment variables from invalid asset paths;
- an unavailable `GenieSim Generator` model or save action from a generation
  failure;
- scene compilation from optional Isaac Sim visualization.

## Validation

Before completion:

- verify every referenced path exists;
- render the Markdown structure for obvious formatting problems;
- run each read-only health/status command or validate it against the running
  stack;
- run the documented compile command with the existing natural-language smoke
  scene configuration where it will not overwrite user data;
- scan the README for OpenAI key patterns and confirm none are present;
- run `git diff --check` on the new document.

## Non-Goals

- Embedding or copying the API key into tracked files.
- Reinstalling Conda, Docker, GenieSim assets, or Isaac Sim.
- Documenting the GPU-based VL embedding profile in depth.
- Automating Open WebUI's first-time configuration import in a new script.
- Changing generator runtime behavior.
