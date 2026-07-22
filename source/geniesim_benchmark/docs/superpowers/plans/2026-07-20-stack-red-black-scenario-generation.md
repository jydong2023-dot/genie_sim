# Red-on-Black Scenario Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and evaluate 40 reproducible red-on-black benchmark scenes, including single-dimension generalization, combined stress cases, and a rendered contact sheet.

**Architecture:** A benchmark-local generator owns the fixed scenario matrix and writes numeric task bundles plus structured metadata. A small loader resolves per-instance background and light overrides while existing USDA scenes continue to own object and table transforms. Preview rendering reuses the current benchmark gallery runner and composes its output into one labeled image.

**Tech Stack:** Python 3.11+, JSON, USDA, NumPy, Pillow, pytest, Isaac Sim/OpenUSD, existing GenieSim benchmark runtime.

**Workspace constraint:** Work in place and do not commit. The repository contains user-owned tracked and untracked changes.

---

### Task 1: Scenario Metadata Loader

**Files:**
- Create: `src/geniesim_benchmark/benchmark/scenario_config.py`
- Test: `tests/test_stack_red_black_scenario_generation.py`

- [ ] **Step 1: Write failing loader tests**

Add tests that create a temporary `<task>/<id>/scenario.json`, then assert:

```python
scenario = load_scenario_config(task_dir, 12)
assert scenario.instance_id == 12
assert scenario.background_usd == "background/room/room_2/background.usda"
assert scenario.light_config == {"temperature": 5000, "intensity": 1000}
assert load_scenario_config(task_dir, 99) is None
```

Also assert malformed IDs and non-dictionary light configs raise `ValueError`
with the scenario path in the message.

- [ ] **Step 2: Verify RED**

Run:

```bash
cd source/geniesim_benchmark
PYTHONPATH=src pytest tests/test_stack_red_black_scenario_generation.py -q
```

Expected: collection fails because `geniesim_benchmark.benchmark.scenario_config`
does not exist.

- [ ] **Step 3: Implement the focused loader**

Define an immutable model and loader:

```python
@dataclass(frozen=True)
class ScenarioConfig:
    instance_id: int
    split: str
    dimension: str
    background_usd: str | None
    light_config: dict[str, int]


def load_scenario_config(task_dir: Path, instance_id: int) -> ScenarioConfig | None:
    path = task_dir / str(instance_id) / "scenario.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Validate identity and the narrow runtime-owned fields before returning.
```

Keep generation-only values under `parameters` in raw JSON; the runtime loader
does not need to model object poses or table height.

- [ ] **Step 4: Verify GREEN**

Run the Task 1 command. Expected: all loader tests pass.

### Task 2: Deterministic Scenario Generator

**Files:**
- Create: `scripts/generate_stack_red_black_scenarios.py`
- Modify: `tests/test_stack_red_black_scenario_generation.py`

- [ ] **Step 1: Write failing scenario-matrix tests**

Import the script module by file path and assert:

```python
specs = build_scenario_specs(seed=20260720)
assert len(specs) == 40
assert [s.instance_id for s in specs] == list(range(40))
assert Counter(s.dimension for s in specs) == {
    "baseline": 1,
    "object_pose": 11,
    "background": 6,
    "lighting": 8,
    "table_height": 4,
    "combined": 10,
}
assert build_scenario_specs(20260720) == build_scenario_specs(20260720)
assert build_scenario_specs(20260720) != build_scenario_specs(20260721)
```

For every spec, check XY bounds, yaw bounds, minimum separation, supported
background, supported light values, and the four exact table offsets.

- [ ] **Step 2: Verify RED**

Run the focused test file. Expected: failure because the generator script does
not exist.

- [ ] **Step 3: Implement scenario sampling**

Use a local `random.Random(seed)` and immutable `ScenarioSpec`. Keep these
constants in the script:

```python
ROOT_SEED = 20260720
X_RANGE = (-0.20, 0.12)
Y_RANGE = (-0.22, 0.22)
YAW_RANGE_DEG = (-30.0, 30.0)
MIN_SEPARATION = 0.12
TABLE_HEIGHT_OFFSETS = (-0.05, -0.025, 0.025, 0.05)
LIGHT_TEMPERATURES = (3000, 5000, 7000, 9000)
LIGHT_INTENSITIES = (500, 1000, 3000, 6000)
```

Sample pose pairs with bounded rejection and raise a descriptive error after
1000 failed attempts. Standard scenarios copy all baseline parameters except
their declared dimension. Combined scenarios must differ from baseline in all
four requested dimensions.

- [ ] **Step 4: Implement bundle rendering**

Generate `scene.usda` from one script-owned template and serialize JSON with:

```python
json.dumps(payload, indent=2, sort_keys=True) + "\n"
```

The scene template preserves the two cube payloads, black material binding,
kinematic table, and stable prim IDs. Quaternion values are derived from yaw.
Update `scene_info.json` coordinates, quaternion, table Z, seed, and task IDs.
Keep `instructions.json` and `problems.json` semantically identical across
instances.

- [ ] **Step 5: Implement bounded replacement behavior**

The CLI surface is:

```bash
python scripts/generate_stack_red_black_scenarios.py \
  --seed 20260720 \
  --output-dir src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block \
  --replace-generated
```

Without `--replace-generated`, refuse to overwrite numeric directories other
than the existing verified instance 0. With it, remove only numeric directories
and `scenario_manifest.json`; preserve all other files. Write each
`scenario.json` plus root `scenario_manifest.json`.

- [ ] **Step 6: Verify GREEN and determinism**

Run the focused tests. Then generate twice into two temporary directories and
run:

```bash
diff -qr /tmp/stack-red-black-a /tmp/stack-red-black-b
```

Expected: no output and exit code 0.

### Task 3: Serial Runtime Background and Lighting

**Files:**
- Modify: `src/geniesim_benchmark/benchmark/task_benchmark.py`
- Modify: `tests/test_stack_red_black_scenario_generation.py`

- [ ] **Step 1: Write failing runtime-helper tests**

Extract pure helpers and test that:

```python
apply_scenario_to_task_config(task_config, scenario)
assert task_config["scene"]["scene_usd"] == scenario.background_usd

apply_scenario_to_env(env, scenario)
env.set_light_config.assert_called_once_with(scenario.light_config)
```

`None` scenarios and empty overrides must preserve existing behavior.

- [ ] **Step 2: Verify RED**

Run the focused test file. Expected: helpers are absent.

- [ ] **Step 3: Implement and wire serial helpers**

Before `create_env`, load the instance scenario and apply its background to a
deep copy of the original task configuration. After environment construction,
set its fixed light config before the existing call to
`env.apply_generalization()`. Restore the baseline task configuration for the
next instance so overrides cannot leak.

Keep tasks without `scenario.json` byte-for-byte behaviorally unchanged.

- [ ] **Step 4: Verify GREEN**

Run the focused tests and the existing red-on-black task tests. Expected: pass.

### Task 4: Vectorized Background Guard

**Files:**
- Modify: `src/geniesim_benchmark/benchmark/task_benchmark.py`
- Modify: `tests/test_stack_red_black_scenario_generation.py`

- [ ] **Step 1: Write failing guard tests**

Test a pure resolver:

```python
assert resolve_vector_background([same, same]) == same
with pytest.raises(ValueError, match="different backgrounds"):
    resolve_vector_background([room_2, room_3])
```

- [ ] **Step 2: Verify RED**

Run the focused test. Expected: resolver is absent.

- [ ] **Step 3: Implement and wire the guard**

Resolve all batch scenario configs before `_evaluate_vectorized_sync` loads the
stage. Permit zero or one distinct background; raise an actionable exception
listing instance IDs and backgrounds when a batch contains more than one.
Apply homogeneous fixed lighting only when all batch entries match; otherwise
raise rather than applying the wrong light config to cloned environments.

- [ ] **Step 4: Verify GREEN**

Run focused and full offline benchmark tests. Expected: all pass.

### Task 5: Generate and Statistically Validate 40 Bundles

**Files:**
- Create: `src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/{1..39}/*`
- Create: `src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/{0..39}/scenario.json`
- Create: `src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/scenario_manifest.json`
- Modify: `src/geniesim_benchmark/config/g2op_spatial_stack_red_block_on_black_block.yaml`
- Modify: `tests/test_stack_red_block_on_black_block_task.py`

- [ ] **Step 1: Update task contract tests for 40 instances**

Assert numeric directories are exactly `0..39`, every bundle has five files,
and manifest entries match per-instance scenarios. Parameterize the existing
scene/material/instruction/problem checks over all 40 instances.

- [ ] **Step 2: Verify RED**

Run both task-specific test files. Expected: missing generated instances and
manifest failures.

- [ ] **Step 3: Generate repository artifacts**

Run the generator with the canonical seed and output directory. Add
`num_instances: 0` to the entry YAML explicitly so the committed config states
that all numeric instances are evaluated.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
cd source/geniesim_benchmark
PYTHONPATH=src pytest tests/test_stack_red_block_on_black_block_task.py \
  tests/test_stack_red_black_scenario_generation.py -q
```

Expected: all task and generator contract tests pass.

### Task 6: Render Preview Gallery and Contact Sheet

**Files:**
- Create: `scripts/build_stack_red_black_contact_sheet.py`
- Create: `task_previews/stack_red_block_on_black_block/contact_sheet.png`
- Modify: `src/geniesim_benchmark/scripts/preview_task_gallery.py`
- Modify: `tests/test_stack_red_black_scenario_generation.py`
- Modify: `README_STACK_RED_BLOCK_ON_BLACK_BLOCK.md`

- [ ] **Step 1: Write failing contact-sheet tests**

Create 40 temporary colored thumbnails and assert the builder emits a nonblank
image with a fixed `5 x 8` tile layout, all 40 labels, and deterministic size.
Assert missing instance images produce a clear error listing IDs.

- [ ] **Step 2: Verify RED**

Run the focused test. Expected: contact-sheet module is absent.

- [ ] **Step 3: Implement the contact-sheet builder**

Use Pillow to resize without distortion, letterbox each image, add labels such
as `12 background`, and save a PNG. The CLI accepts the preview root, manifest,
camera name, and output path. It validates tile count and per-image variance
before saving.

- [ ] **Step 4: Verify contact-sheet tests**

Run the focused test. Expected: pass.

- [ ] **Step 5: Extend the existing gallery with instance-count passthrough**

Add `--num-instances` to `preview_task_gallery.py`, defaulting to `1` to
preserve current behavior. Pass its integer value to `build_preview_command()`
as `--benchmark.num_instances=<value>`. Test both the default command and value
`0`, which tells the benchmark runtime to iterate every numeric directory in
sorted order.

- [ ] **Step 6: Validate USD composition and render all instances**

Use the existing GenieSim Isaac container. First compose all 40 background and
subscene pairs against `/geniesim_assets`. Then run the task through the gallery
with `--num-instances 0`. The benchmark iterates instance IDs in sorted order;
the gallery archives each camera stream in that order and records the instance
ID alongside each image in its metadata.

Every run must exit 0, produce a nonblank policy-camera frame, and report initial
`Ontop = 0`. Do not accept a background that collides with or hides the table.

- [ ] **Step 7: Build and inspect the real contact sheet**

Generate:

```text
task_previews/stack_red_block_on_black_block/contact_sheet.png
```

Inspect the image for cube colors, separation, reachability, table-height
changes, six backgrounds, and light variation. If a candidate background fails,
stop and report it as required by the approved design.

- [ ] **Step 8: Document generation and preview commands**

Update the task README with canonical regeneration, full evaluation, split
interpretation, and contact-sheet commands. State that mixed-background vector
batches are unsupported.

### Task 7: Final Verification

**Files:**
- Verify all files changed above.

- [ ] **Step 1: Run offline verification**

```bash
cd source/geniesim_benchmark
PYTHONPATH=src pytest tests -q
python -m py_compile \
  scripts/generate_stack_red_black_scenarios.py \
  scripts/build_stack_red_black_contact_sheet.py \
  src/geniesim_benchmark/benchmark/scenario_config.py \
  src/geniesim_benchmark/benchmark/task_benchmark.py
```

Expected: tests pass and compilation exits 0.

- [ ] **Step 2: Check repository diff quality**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; status contains only pre-existing user changes
and files intentionally added or modified by this feature.

- [ ] **Step 3: Confirm simulator evidence**

Record the number of composed scenes, successful previews, nonblank frames,
initial failed `Ontop` checks, and contact-sheet path in the task README and
session handoff.
