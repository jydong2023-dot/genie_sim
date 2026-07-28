# Genie Sim Code Analysis Plan

## Goal
Analyze `/home/user/djy/genie_sim` and summarize architecture, major modules, execution flow, dependencies, and notable risks.

## Phases
| Phase | Status | Notes |
|---|---|---|
| 1. Repository orientation | complete | Read agent instructions, top-level docs, package map. |
| 2. Module inventory | complete | Inspected package layouts, metadata, and independent modules. |
| 3. Core flow analysis | complete | Traced CLI, ROS, benchmark, generator, teleop, world, data collection, RLinf, and reconstruction entry points. |
| 4. Quality and risk review | complete | Checked tests, automation hooks, generated artifacts, dependency boundaries, and existing modified files. |
| 5. Final summary | complete | Provide concise Chinese report with references. |
| 6. Focused `geniesim_benchmark` analysis | complete | Re-audited package structure, execution/data flows, configs, tests, and current local additions. |
| 7. Two-block stacking task design | complete | User approved the ordered red-on-black design, G2 Omnipicker, and task-local black material override. |
| 8. Red-on-black implementation | complete | Added the reference README, instance 0 task bundle, registrations, static and checker tests; OpenUSD composition and G2 headless preview passed. |
| 9. `geniesim-generator` environment audit | complete | Environment imports and compiler execute, but generated USD payload paths are invalid; MCP stack/profile and Isaac preview prerequisites are not currently complete. |
| 10. Generator path-resolution design | complete | Approved compatibility contract documented, self-reviewed, and committed as `0116574`; awaiting explicit spec review before implementation planning. |
| 11. Generator path-resolution implementation plan | complete | TDD plan covered every approved resolution/error/test requirement; user selected inline execution in an isolated worktree. |
| 12. Generator path-resolution implementation | complete | Implemented in isolated worktree, verified with 12 tests and real OpenUSD composition, merged to `main` as `ab050e2`, then cleaned up the worktree/branch. |
| 13. Natural-language scene generation deployment | complete | OpenAI-backed asset search and Open WebUI are running from `main`; a Chinese prompt produced and compiled `openai_nl_smoke/0`, and merged-result verification passed. |
| 14. Open WebUI save-action compatibility fix | complete | Added Responses/raw-DSL extraction, stale-reply protection, deterministic export metadata sync, 8 regression tests, and deployed 0.2.0 to the healthy live Open WebUI instance. |
| 15. Generic LLM-task scenario augmentation | complete | Added a config-driven generic engine and CLI mode, pose/table USD overrides, runtime lighting configs, portable color/texture materials, synchronized metadata, safe source staging, docs/profile, legacy compatibility, 33 passing tests, and real table/no-table smoke generation with OpenUSD validation. |
| 16. Remove red/black generator legacy mode | complete | Replaced the old entry with required-task `generate_task_scenarios.py`, deleted all hard-coded red/black generator logic and legacy tests, migrated active docs, passed 28 tests, and validated 10 OpenUSD stages across table/no-table tasks. |
| 17. In-place augmentation and preview gallery | complete | Appends after the highest numeric instance by default, replaces on request, previews exactly the generated IDs, saves three cameras per instance, and builds a contact sheet; 43 tests and append/replace/dry-run smoke checks passed. |
| 18. Host/container execution runbook | complete | Verified the stable 5.1 image/container, live mounts and user environment, correct task/YAML name, exact host startup and container execution commands, output paths, replacement flow, and teardown. |
| 19. Extract `scene_augmentation` package | complete | Added the sibling package and standalone CLI, moved generator/contact-sheet core, retained Benchmark preview/runtime adapters and compatibility imports, wired bootstrap/Docker/docs, built a wheel, and passed 46 tests plus standalone/adapter smokes. |
| 20. Regenerate `s2r` initial-scene previews | complete | Rendered all 8 matching configs in Isaac preview mode with zero inference connections, enlarged the instruction overlay to 29 px glyph height at 1280 px, verified 24 camera images, and refreshed the 8 delivered previews plus collage. |

## Constraints
- Treat existing user changes as owned by the user.
- Do not modify source code during analysis.
- Prefer repository docs and source evidence over assumptions.
- Current request is design guidance only; do not create the task files until the user approves the design.
- User approved the design and explicitly requested implementation in the current benchmark checkout.
- Work in place without commits: the repository is on `main`, but the benchmark test directory contains user-owned untracked work that would not be present in a new worktree.
- The current request is read-only diagnosis: do not install, upgrade, or modify packages in `geniesim-generator` without explicit authorization.
- User explicitly requested a permanent fix for the Open WebUI `No code blocks found` failure; source, export, tests, and documentation are in scope.
- User explicitly requested the generic generator use a new task-neutral name and that the prior red/black compatibility mode and all task-specific generator code be removed.
- For phase 20, select tasks from `source/geniesim_benchmark/src/geniesim_benchmark/config` whose task/config name contains `s2r`; render initial scenes only, do not execute inference, and make instruction text visibly larger than in the prior previews.

## Errors Encountered
| Error | Attempt | Resolution |
|---|---|---|
| Combined phase-20 planning patch referenced the wrong `findings.md` heading | 1 | Inspect the three file headers, then apply a narrowly anchored patch using each file's actual heading. |
| First enlarged overlay scale produced 26 px glyphs, below the 28 px regression target | 1 | Measure candidate OpenCV scales directly; use a 1.4 cap (`width / 900`) so 1280 px previews produce 29 px glyphs with margin. |
| Host artifact verification treated container metadata paths under `/workspace` as host absolute paths | 1 | Map each metadata image path relative to `/workspace` back onto the repository root, then rerun the assertions without changing generated artifacts. |
| Open WebUI official-doc web search returned a response decode error | 1 | Use a direct fetch from the official Open WebUI documentation instead of retrying the same search. |
| Isolated worktree creation triggered a Git LFS smudge failure because the repository exceeded its LFS budget | 1 | Inspect the partial worktree state, then recreate with `GIT_LFS_SKIP_SMUDGE=1`; generator tests do not require the unrelated robot mesh payloads. |
| `pytest` collection: `ModuleNotFoundError: geniesim_benchmark` | 1 | Diagnose as uninstalled `src/` layout; rerun with target `src` on `PYTHONPATH` without changing code. |
| Preview facade root-fallback test returned `/home/user` | 1 | The import facade re-exported a function whose globals still belonged to the root script, so monkeypatching the facade did not affect `package_root`; add a facade-local root resolver and rerun the suite. |
| Final `py_compile` could not write `scripts/__pycache__` | 1 | The source tree cache is read-only in this environment; rerun with `PYTHONPYCACHEPREFIX=/tmp/geniesim-benchmark-pycache` so compilation remains non-mutating. |
| Host real-preview smoke failed creating `/workspace` and could not expose Isaac Sim extension | 1 | The host Conda CLI is configured for the container's `/workspace` layout and cannot launch Isaac from this restricted host shell. Preserve the failure metadata in `/tmp`; rely on the passing command/dry-run/archive/contact tests and document that real rendering must run in the configured simulator container/runtime. |
| Initial package extraction patch could not create new parent directories | 1 | `apply_patch` cannot create the new package directory tree itself; create empty directories with `mkdir -p`, then reapply all file content through `apply_patch`. |
| Sandboxed `mkdir -p source/scene_augmentation/...` was read-only | 1 | The new sibling is outside the configured writable root; rerun only the scoped directory-creation command with escalated filesystem permission, then continue all content edits with `apply_patch`. |
| First standalone smoke produced no scenes | 1 | `python -m scene_augmentation.cli` loaded the module but `cli.py` lacked a `__main__` guard; add the guard and rerun with explicit exit checks. |
| Wheel build used default Python 3.13, outside package `<3.13` contract | 1 | Build the wheel through the existing supported `geniesim` Python 3.11 environment instead of weakening the repository-wide Python constraint. |
| Combined documentation patch missed the exact root AGENTS table context | 1 | Inspect the narrow root AGENTS ranges and reapply the planning/error, module-tree, and guide-row edits with exact anchors. |
| `geniesim tool docs --scope cli` reported 12 broken links | 1 | All reported links are pre-existing consequences of the user-owned deleted root `README.md` or unrelated data-collection docs; the new package passed coverage/index checks and introduced no listed violation. Keep scoped tests/DAG/diff checks as migration gates. |
| Asset-count `python3 -c` syntax error from literal `\\n` | 1 | Replace loop/newline script with a single-expression read-only command. |
| Reference instance `stack_three_building_blocks/0/graph.dot` not found | 1 | Classified graph artifacts as optional because the packaged runnable instance omits them. |
| No in-package reference to `task_config_mapping.py` found | 1 | Treat `TASK_MAPPING` registration as catalog metadata, not a runtime requirement; verify required lookups separately. |
| Repo-local asset-index search returned no match | 1 | Located the separately maintained asset checkout at `/home/user/djy/geniesim_assets`; inspect its canonical index instead. |
| Broad black-color scene search produced unrelated balls/bottles and truncated output | 1 | Narrow subsequent lookup to building-block/cube entries in the asset index. |
| Initial one-line Python query for dark building blocks had mismatched parentheses | 1 | Replaced it with a direct `rg` scan of authoritative `description.py` files; no files were changed. |
| First material search used a duplicated `src/geniesim_benchmark` path | 1 | Re-ran against `benchmark/config/llm_task`; no source changes occurred. |
| Direct `sed` of payload `Aligned.usd` emitted binary data | 1 | Treat the payload as binary USD and use USD-aware tooling/runtime material code for further inspection. |
| Default Python cannot import `pxr` for standalone USD composition validation | 1 | Use the project `geniesim`/Isaac Sim runtime for scene parsing and preview; retain static contract checks as offline coverage only. |
| Host `geniesim` command and common `/isaac-sim` paths are absent | 1 | Inspect the existing running `geniesim3` container and existing Conda environments instead of installing a new runtime. |
| Documentation `rg` command referenced root `README.md` from `/home/user/djy/genie_sim` where it is currently deleted | 1 | Use the package README and preserved findings; this unrelated user-owned deletion does not affect the task. |
| Container `/isaac-sim/python.sh` cannot directly import `pxr` | 1 | Inspect the launcher/environment and use the Kit/SimulationApp entry path or host `geniesim` Conda USD bindings instead of repeating the bare import. |
| `geniesim benchmark run --help` treats `--help` as a config selector | 1 | Use the known CLI syntax from package docs and query `benchmark list`; do not rely on subcommand help for this CLI path. |
| Container Kit startup cannot find NumPy's bundled `libgfortran-040039e1.so.5.0.0` | 1 | Locate the library in the image and add its directory to `LD_LIBRARY_PATH` for the validation process before retrying. |
| Generator smoke test exits 0 but OpenUSD cannot open the asset payload | 1 | Traced `ASSETS_INDEX.url` through `app.py` into `utils/usd.py`; serializer hardcodes nonexistent `source/geniesim_generator/src/assets` instead of the installed `/home/user/djy/geniesim_assets`. No fix applied during the read-only audit. |
| `py_compile` cannot write into generator `__pycache__` | 1 | Existing cache directory is owned by `nobody:nogroup`; reran with `PYTHONPYCACHEPREFIX=/tmp/...`, and compilation passed without changing the source cache. |
| New save-action tests failed to import `aiofiles` under the default Python | 1 | The action belongs to the generator `mcp` extra; run its tests in the existing `geniesim-generator` Conda environment, which contains the declared optional dependency. |
| `conda run -n geniesim-generator pytest` still used an external pytest interpreter without `pydantic` | 1 | Invoke `python -m pytest` through the environment so module execution is tied to its Python interpreter. |
| Generator Conda environment has no `pytest` module | 1 | The new suite uses stdlib `unittest`; execute the test file directly with the environment's Python instead of installing packages. |
| Standalone Open WebUI token generation reported `HMAC key must not be empty` | 1 | The app process owns a persisted session secret that a bare container Python process does not initialize; use the persisted secret without exposing it, or fall back to a backed-up transactional SQLite update followed by cache refresh/restart. |
| Live function inspection queried nonexistent `function.active` columns | 1 | This Open WebUI schema stores enable/global state outside those columns; inspect `PRAGMA table_info(function)` and update only the verified content/metadata fields. |
| Host-side SQLite update failed with `attempt to write a readonly database` | 1 | The bind-mounted database is owned by the container service account. Preserve the completed SQLite backup in `/tmp`, then perform the same narrow transaction inside the container where the service owns the database. |
| First health request immediately after `docker restart` could not connect | 1 | Open WebUI was still starting; poll the health endpoint for a bounded interval and inspect startup logs if it does not become ready. |
| Broader generator pytest collection failed because default Python lacks `pxr` | 1 | This is an existing OpenUSD runtime prerequisite unrelated to the save action. Keep the targeted 8-test Conda suite, compile checks, export parity, live hash, and real-chat extraction as the scoped verification. |
| Sample task path `sort_the_fruit_into_the_box_apple/0` did not exist | 1 | Discover actual task directory names under `llm_task` before selecting heterogeneous fixtures; do not assume the eval YAML subtask spelling matches the bundle directory. |
| Benchmark pytest emitted a read-only `.pytest_cache` warning | 1 | Tests themselves passed; use `-p no:cacheprovider` for subsequent runs so verification does not attempt to write into the user-owned package cache. |
| Generic test could not import the non-package `scripts` directory | 1 | Match the existing generator tests by loading the script module from its file path with `importlib.util`; do not turn the operational scripts directory into a Python package solely for tests. |
| Default generic profile rejected a real task with no table | 1 | Make table discovery optional, omit table-only dimensions when no table exists, and let pose/light augmentation remain usable for arbitrary non-table tasks. |
| Full benchmark test collection failed on missing `geniesim_benchmark.scripts.preview_task_gallery` | 1 | This is unrelated pre-existing untracked gallery coverage. Run the benchmark suite excluding that missing user-owned module, while retaining all scenario/task tests in scope. |
| Final smoke task `clean_the_desktop_test` was no longer present | 1 | The task existed during the previous turn but has since been removed from the working tree. Use the packaged no-table task `sorting_packages_continuous/0` for the generic no-table smoke instead of retrying the missing path. |
| Final stale-reference scan used package-relative paths from the repository root | 1 | Re-run the scan from `source/geniesim_benchmark` (or prefix every path); no file mutation occurred. |
