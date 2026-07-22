# Red Block on Black Block Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and validate one G2 Omnipicker benchmark instance in which the red cube must be placed on top of the black cube.

**Architecture:** Reuse `table_task_2_g2_op`, the existing 5 cm cube asset, and the existing ordered `Ontop` checker. Make one cube visually black with a task-local USD material override, then register the new subtask in the robot-init, scoring, and catalog dictionaries.

**Tech Stack:** Python 3.10+, pytest, YAML/JSON, OpenUSD USDA, Isaac Sim benchmark runtime.

---

### Task 1: Preserve the Approved Design

**Files:**
- Create: `README_STACK_RED_BLOCK_ON_BLACK_BLOCK.md`
- Create: `docs/superpowers/plans/2026-07-20-stack-red-block-on-black-block.md`

- [x] **Step 1: Write the reference README**

Document the task name, reused G2 eval task, reused cube asset, scene material override, ordered `Ontop(red, black)` contract, file list, registrations, and validation matrix.

- [x] **Step 2: Check documentation formatting**

Run:

```bash
git diff --check -- README_STACK_RED_BLOCK_ON_BLACK_BLOCK.md docs/superpowers/plans/2026-07-20-stack-red-block-on-black-block.md
```

Expected: exit code 0 and no output.

### Task 2: Add a Failing Static Contract Test

**Files:**
- Create: `tests/test_stack_red_block_on_black_block_task.py`

- [x] **Step 1: Write tests for the complete task contract**

The test module must parse task data without importing Isaac Sim. It must assert:

```python
TASK_NAME = "stack_red_block_on_black_block"
RED_ID = "red_block_000"
BLACK_ID = "black_block_000"

assert config["benchmark"]["task_name"] == "table_task_2_g2_op"
assert config["benchmark"]["platform"] == "g2_op"
assert config["benchmark"]["sub_task_name"] == TASK_NAME
assert scene.count("benchmark_building_blocks_074/Aligned.usda") == 2
assert 'def Material "BlackMaterial"' in scene
assert 'rel material:binding = </World/Objects/black_block_000/Looks/BlackMaterial>' in scene
assert metadata["layout"][RED_ID]["description"]["color"] == "red"
assert metadata["layout"][BLACK_ID]["description"]["color"] == "black"
assert instructions["instructions"][0]["instruction"] == "place the red block on top of the black block"
assert wait_any[0] == {"Ontop": "red_block_000|black_block_000"}
assert TASK_STEPS[TASK_NAME] == ["Ontop"]
```

Use AST parsing to check `TASK_INFO_DICT`, `TASK_STEPS`, and `TASK_MAPPING` without importing simulation modules.

- [x] **Step 2: Run the test and verify RED**

Run:

```bash
PYTHONPATH=src pytest tests/test_stack_red_block_on_black_block_task.py -q
```

Expected: FAIL because the task YAML and bundle do not exist yet.

### Task 3: Add Instance 0 Task Data

**Files:**
- Create: `src/geniesim_benchmark/config/g2op_spatial_stack_red_block_on_black_block.yaml`
- Create: `src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/0/scene.usda`
- Create: `src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/0/scene_info.json`
- Create: `src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/0/instructions.json`
- Create: `src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/0/problems.json`

- [x] **Step 1: Add the entry YAML**

Create:

```yaml
app:
  enable_rate_limit: true
  enable_ros: false
benchmark:
  task_name: table_task_2_g2_op
  platform: g2_op
  sub_task_name: stack_red_block_on_black_block
  seed: 1
  model_arc: corobot
  num_episode: 1
  record: false
```

- [x] **Step 2: Add the scene**

Create the same table payload as `stack_three_building_blocks/0`. Add
`red_block_000` at `(-0.16, -0.14, 0.885)` and `black_block_000` at
`(-0.04, 0.16, 0.885)`. Both payload
`benchmark_building_blocks_074/Aligned.usda`. Define a black
`UsdPreviewSurface` under the black prim and bind it to
`black_block_000/entity/body/visual`.

- [x] **Step 3: Add synchronized metadata**

Create a layout with exactly `red_block_000`, `black_block_000`, and
`table_614a6115`. Both blocks have dimensions `[0.05, 0.05, 0.05]` and asset ID
`benchmark_building_blocks_074`; their colors are `red` and `black`. Create a
directed relation graph whose only object leaves are those three layout IDs.

- [x] **Step 4: Add the instruction**

Create:

```json
{
  "instructions": [
    {"instruction": "place the red block on top of the black block"}
  ],
  "task_id": "stack_red_block_on_black_block_0"
}
```

- [x] **Step 5: Add the problem**

Create one `ActionSetWaitAny` containing exactly:

```json
[
  {"Ontop": "red_block_000|black_block_000"},
  {"Onfloor": "red_block_000|0"},
  {"Onfloor": "black_block_000|0"},
  {"StepOut": 1500}
]
```

Set `Problem` to `stack_red_block_on_black_block`.

### Task 4: Register the New Subtask

**Files:**
- Modify: `src/geniesim_benchmark/benchmark/config/robot_init_states.py`
- Modify: `src/geniesim_benchmark/plugins/output_system/eval_utils.py`
- Modify: `src/geniesim_benchmark/benchmark/config/task_config_mapping.py`

- [x] **Step 1: Register G2 initial state**

Add next to `stack_three_building_blocks`:

```python
"stack_red_block_on_black_block": {
    "G2_omnipicker": G2_DEFAULT_STATES,
},
```

- [x] **Step 2: Register scoring**

Add to `TASK_STEPS`:

```python
"stack_red_block_on_black_block": ["Ontop"],
```

- [x] **Step 3: Register catalog metadata**

Add next to the other stack tasks:

```python
"stack_red_block_on_black_block": {
    "background": {
        "G2": "table_task_2_g2_op",
    },
    "eval_dims": {"manip": "spatial_pick_place", "cognition": "semantic"},
},
```

- [x] **Step 4: Run the contract test and verify GREEN**

Run:

```bash
PYTHONPATH=src pytest tests/test_stack_red_block_on_black_block_task.py -q
```

Expected: all tests in the module pass.

### Task 5: Offline Validation

**Files:**
- Verify all files created or modified above.

- [x] **Step 1: Parse JSON and YAML through tests**

Run:

```bash
PYTHONPATH=src pytest tests -q
```

Expected: all benchmark tests pass.

- [x] **Step 2: Compile modified Python modules**

Run:

```bash
python -m py_compile \
  src/geniesim_benchmark/benchmark/config/robot_init_states.py \
  src/geniesim_benchmark/plugins/output_system/eval_utils.py \
  src/geniesim_benchmark/benchmark/config/task_config_mapping.py
```

Expected: exit code 0 and no output.

- [x] **Step 3: Validate formatting and inspect scope**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only user-owned prior changes plus the documented
task files and three registrations are present.

### Task 6: Isaac Sim Preview and Checker Validation

**Files:**
- Runtime validation only; do not modify files unless a verified defect is found.

- [x] **Step 1: Run one headless preview**

Run:

```bash
geniesim benchmark run g2op_spatial_stack_red_block_on_black_block \
  --app.headless=true \
  --benchmark.preview=true \
  --benchmark.num_episode=1 \
  --benchmark.num_instances=1 \
  --benchmark.enable_vec=0 \
  --benchmark.record=false
```

Expected: process exits successfully and writes head, left-hand, and right-hand
preview images showing exactly one red cube and one black cube on the table.

Observed: the container run exited with code 0 and wrote all three images under
`debug_preview/`. The head and left-hand views clearly show one red cube and one
black cube, separated and reachable on the table. The initial evaluation score
was 0, as required before policy execution.

- [x] **Step 2: Check the ordered success matrix**

Validate in simulation:

```text
red beside black                         -> Ontop score 0
black on red                             -> Ontop score 0
red on black with projected overlap <50% -> Ontop score 0
red on black with projected overlap >=50%-> Ontop score 1
```

Observed: `test_existing_ontop_checker_enforces_order_and_overlap` executes the
repository's `Ontop.update()` implementation against the four controlled AABB
states. The actual preview independently covers the initial separated state.

- [x] **Step 3: Record any environment blocker honestly**

If Isaac Sim, a display/GPU, or an inference endpoint is unavailable, report the
exact command and failure. Do not represent offline validation as simulator
validation.

No remaining blocker. The existing `geniesim3` container required NumPy's
bundled library directory in `LD_LIBRARY_PATH`, after which full payload
composition and the headless benchmark preview both succeeded.

No commit is created in this execution because the user requested workspace
changes but did not request a commit, and the checkout contains unrelated
user-owned modifications.
