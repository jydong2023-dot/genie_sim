# Generator Path Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate composition-valid USD files in the real benchmark task directory regardless of editable-install or deployed package layout.

**Architecture:** Add one focused `paths.py` module that owns environment override, installed-package, and sibling-checkout discovery. `app.py` consumes its output-root resolver, while `utils/usd.py` consumes its validated asset-path resolver; both resolve at call time so environment changes are visible.

**Tech Stack:** Python 3.11, `pathlib`, `importlib.util`, OpenUSD `pxr`, standard-library `unittest`, subprocess smoke testing.

---

### Task 1: Path Resolution API

**Files:**
- Create: `source/geniesim_generator/src/geniesim_generator/paths.py`
- Create: `source/geniesim_generator/tests/__init__.py`
- Create: `source/geniesim_generator/tests/test_paths.py`

- [x] **Step 1: Write failing resolver tests**

Create standard-library tests for these concrete behaviors:

```python
class PathResolutionTests(unittest.TestCase):
    def test_assets_override_wins(self): ...
    def test_assets_fall_back_to_installed_package(self): ...
    def test_invalid_assets_override_fails(self): ...
    def test_output_override_wins(self): ...
    def test_output_falls_back_to_importable_benchmark(self): ...
    def test_output_falls_back_to_sibling_checkout(self): ...
    def test_missing_output_root_explains_override(self): ...
    def test_resolve_asset_path_rejects_missing_payload(self): ...
```

Use `tempfile.TemporaryDirectory`, `unittest.mock.patch.dict`, and patched
`find_spec` results. Every successful asset root contains `__init__.py`; every
successful output root is an existing directory.

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
conda run -n geniesim-generator python -m unittest \
  source/geniesim_generator/tests/test_paths.py -v
```

Expected: import failure for missing `geniesim_generator.paths`.

- [x] **Step 3: Implement the minimal resolver**

Create `paths.py` with this public contract:

```python
ASSETS_DIR_ENV = "GENIESIM_ASSETS_DIR"
OUTPUT_DIR_ENV = "GENIESIM_GENERATOR_OUTPUT_DIR"

def resolve_assets_root() -> Path:
    """Return a validated asset package directory."""

def resolve_generator_output_root() -> Path:
    """Return the real benchmark `llm_task` directory."""

def resolve_asset_path(asset_url: str | os.PathLike[str]) -> Path:
    """Resolve and validate one indexed asset payload."""
```

Resolution order must exactly match the approved design. Use
`importlib.util.find_spec` rather than importing packages, validate explicit
overrides without fallback, and include the controlling environment variable
in every configuration error.

- [x] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: eight tests pass.

- [x] **Step 5: Commit the resolver**

```bash
git add source/geniesim_generator/src/geniesim_generator/paths.py \
  source/geniesim_generator/tests/__init__.py \
  source/geniesim_generator/tests/test_paths.py
git commit -m "fix(generator): resolve installed asset and output roots"
```

### Task 2: Composition-Valid USD Payloads

**Files:**
- Modify: `source/geniesim_generator/src/geniesim_generator/utils/usd.py`
- Create: `source/geniesim_generator/tests/test_usd_paths.py`

- [x] **Step 1: Write the failing USD test**

Build a temporary asset package containing a minimal USDA payload with a
default prim and child mesh, set `GENIESIM_ASSETS_DIR`, call
`gen_scene_usda()`, and assert:

```python
payload = prim.GetMetadata("payload").GetAddedOrExplicitItems()[0]
resolved = (scene_path.parent / payload.assetPath).resolve()
self.assertEqual(resolved, asset_file.resolve())
self.assertTrue(resolved.is_file())
self.assertTrue(stage.GetPrimAtPath("/World/Objects/test_asset/Visual").IsValid())
```

Also assert that a missing indexed asset raises `FileNotFoundError` before the
scene is saved.

- [x] **Step 2: Run the USD test and verify RED**

```bash
conda run -n geniesim-generator python -m unittest \
  source/geniesim_generator/tests/test_usd_paths.py -v
```

Expected: generated payload resolves under the nonexistent package-local
`src/assets`, or the missing-payload assertion is not raised.

- [x] **Step 3: Route all USD asset lookups through `resolve_asset_path`**

In `utils/usd.py`:

```python
from pathlib import Path
from geniesim_generator.paths import resolve_asset_path
```

Remove `GENIESIM_PATH` and `ASSETS_PATH`. In `gen_scene_usda()` and
`add_objects_to_stage()`, resolve `object_info["url"]` through
`resolve_asset_path()`, then author `os.path.relpath(object_path,
Path(scene_path).parent)`. Treat scene/output paths as caller-provided paths;
do not prefix them with an asset directory.

- [x] **Step 4: Run resolver and USD tests**

```bash
conda run -n geniesim-generator python -m unittest discover \
  -s source/geniesim_generator/tests -v
```

Expected: all resolver and USD tests pass with no unresolved-payload warning.

- [x] **Step 5: Commit USD path handling**

```bash
git add source/geniesim_generator/src/geniesim_generator/utils/usd.py \
  source/geniesim_generator/tests/test_usd_paths.py
git commit -m "fix(generator): author payloads from installed assets"
```

### Task 3: Benchmark Output and End-to-End Demo

**Files:**
- Modify: `source/geniesim_generator/src/geniesim_generator/app.py`
- Create: `source/geniesim_generator/tests/test_app_output.py`
- Modify: `source/geniesim_generator/AGENTS.md`
- Modify: `source/geniesim_generator/skills/generate-scene/SKILL.md`

- [x] **Step 1: Write the failing subprocess test**

Run the shipped `app.py` from its required working directory with a temporary
existing `GENIESIM_GENERATOR_OUTPUT_DIR` and the installed asset package root.
Assert the process exits zero, creates exactly one numbered instance with the
five expected files, and every payload in `scene.usda` resolves to an existing
file. Before implementation this must fail because output still lands in
`source/geniesim_generator/src/benchmark`.

- [x] **Step 2: Run the app test and verify RED**

```bash
conda run -n geniesim-generator python -m unittest \
  source/geniesim_generator/tests/test_app_output.py -v
```

Expected: temporary output directory contains no generated scene bundle.

- [x] **Step 3: Resolve output root in `app.py`**

Import and call:

```python
from geniesim_generator.paths import resolve_generator_output_root

output_root = resolve_generator_output_root()
scene_name = args.scene_id or scene_info["scene_id"]
scene_path0_dir = output_root / scene_name
```

Keep the existing numbered-instance behavior and artifact names. Convert paths
to strings only when passing them to APIs that require strings.

- [x] **Step 4: Document overrides and corrected output**

Update `AGENTS.md` and `skills/generate-scene/SKILL.md` to state:

```bash
export GENIESIM_ASSETS_DIR=/path/to/geniesim_assets
export GENIESIM_GENERATOR_OUTPUT_DIR=/path/to/benchmark/config/llm_task
```

Both variables are optional when package/source discovery succeeds. Remove the
claim that editable source output lands in generator-local `src/benchmark`.

- [x] **Step 5: Run the complete test suite and real demo**

```bash
conda run -n geniesim-generator python -m unittest discover \
  -s source/geniesim_generator/tests -v

cd source/geniesim_generator/src/geniesim_generator
conda run -n geniesim-generator python app.py \
  --scene_id generator_path_fix_smoke
```

Expected: all tests pass; the demo writes under the actual benchmark package;
OpenUSD reports no missing payload; all five artifacts exist.

- [x] **Step 6: Run repository hygiene checks**

```bash
env PYTHONPYCACHEPREFIX=/tmp/geniesim-generator-path-fix \
  conda run -n geniesim-generator python -m py_compile \
  source/geniesim_generator/src/geniesim_generator/paths.py \
  source/geniesim_generator/src/geniesim_generator/app.py \
  source/geniesim_generator/src/geniesim_generator/utils/usd.py
git diff --check
```

Expected: both commands exit zero.

- [x] **Step 7: Commit implementation and docs**

```bash
git add source/geniesim_generator/src/geniesim_generator/app.py \
  source/geniesim_generator/tests/test_app_output.py \
  source/geniesim_generator/AGENTS.md \
  source/geniesim_generator/skills/generate-scene/SKILL.md
git commit -m "fix(generator): write scenes to benchmark output"
```
