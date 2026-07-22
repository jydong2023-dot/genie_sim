# Red Block on Black Block Benchmark Task

This document describes how to add and validate the G2 Omnipicker benchmark task
`stack_red_block_on_black_block`.

## Goal

The scene contains one red cube and one black cube. The policy succeeds only when
the red cube is placed on top of the black cube.

The ordered condition is important:

- Red beside black: failure.
- Black on red: failure.
- Red on black with less than 50% XY overlap: failure.
- Red stably on black: success.

## Reused Runtime and Assets

The task reuses:

- G2 Omnipicker through `benchmark/config/eval_tasks/table_task_2_g2_op.json`.
- The existing 5 cm, 0.01 kg red plastic cube
  `benchmark_building_blocks_074` for both object instances.
- The existing ADER `Ontop(active, passive)` checker.
- The existing table and room used by `stack_three_building_blocks`.

There is no true black cube in the current `geniesim_assets` building-block
catalog. The black cube therefore uses the same existing cube geometry with a
task-local black `UsdPreviewSurface` material. No asset file is copied or
modified.

## Files

Add:

```text
src/geniesim_benchmark/config/g2op_spatial_stack_red_block_on_black_block.yaml
src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/0/scene.usda
src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/0/scene_info.json
src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/0/instructions.json
src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/0/problems.json
tests/test_stack_red_block_on_black_block_task.py
```

Modify:

```text
src/geniesim_benchmark/benchmark/config/robot_init_states.py
src/geniesim_benchmark/plugins/output_system/eval_utils.py
src/geniesim_benchmark/benchmark/config/task_config_mapping.py
```

Do not add a new `benchmark/config/eval_tasks/*.json` file. The task reuses
`table_task_2_g2_op`.

## Entry Configuration

The task YAML selects the existing G2 table evaluation environment:

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

## Scene

The scene contains these object prims after it is referenced into the benchmark
workspace:

```text
/Workspace/Objects/red_block_000
/Workspace/Objects/black_block_000
```

Both cube prims payload:

```text
/geniesim_assets/objects/benchmark/building_blocks/benchmark_building_blocks_074/Aligned.usda
```

The cube center height is `0.885` m, matching the existing three-block task. The
initial XY positions must be separated by at least 0.12 m so the checker cannot
pass at reset.

The black object defines a local material and overrides the payload material on
`entity/body/visual`:

```usda
def Scope "Looks"
{
    def Material "BlackMaterial"
    {
        token outputs:surface.connect = <.../BlackShader.outputs:surface>
        def Shader "BlackShader"
        {
            uniform token info:id = "UsdPreviewSurface"
            color3f inputs:diffuseColor = (0.01, 0.01, 0.01)
            float inputs:metallic = 0
            float inputs:roughness = 0.45
            token outputs:surface
        }
    }
}
```

The binding target authored under the scene default prim is
`/World/Objects/black_block_000/Looks/BlackMaterial`. USD reference composition
must remap it to `/Workspace/Objects/black_block_000/Looks/BlackMaterial` at
runtime.

## Scene Metadata

`scene_info.json` is not required by the normal subtask execution path, but it is
part of the benchmark task bundle and is used by offline instruction-generation
tools. Keep it synchronized with `scene.usda`.

Required layout entries:

- `red_block_000`: color `red`, 5 cm dimensions, asset
  `benchmark_building_blocks_074`.
- `black_block_000`: color `black`, 5 cm dimensions, asset
  `benchmark_building_blocks_074`, with the description noting the material
  override.
- `table_614a6115`: the existing workspace table.

The relation graph must contain only the table and these two blocks. Do not copy
stale third-block nodes from `stack_three_building_blocks`.

## Instruction

Use an explicit ordered instruction:

```json
{
  "instructions": [
    {
      "instruction": "place the red block on top of the black block"
    }
  ],
  "task_id": "stack_red_block_on_black_block_0"
}
```

Avoid an ambiguous instruction such as `stack the blocks`.

## Evaluation Contract

The first argument to `Ontop` is the active object and the second is the passive
object. The required success leaf is therefore:

```json
{"Ontop": "red_block_000|black_block_000"}
```

The full `ActionSetWaitAny` also contains two fall guards and a timeout:

```json
[
  {"Ontop": "red_block_000|black_block_000"},
  {"Onfloor": "red_block_000|0"},
  {"Onfloor": "black_block_000|0"},
  {"StepOut": 1500}
]
```

Do not use `Stack`; that checker is order-independent. `Ontop` checks that the
red block bottom is within 2 cm of the black block top and that their projected
XY overlap is at least 50%.

## Registrations

Register the G2 initial state in `TASK_INFO_DICT`:

```python
"stack_red_block_on_black_block": {
    "G2_omnipicker": G2_DEFAULT_STATES,
},
```

Register the score leaf in `TASK_STEPS`:

```python
"stack_red_block_on_black_block": ["Ontop"],
```

Register task catalog metadata in `TASK_MAPPING`:

```python
"stack_red_block_on_black_block": {
    "background": {"G2": "table_task_2_g2_op"},
    "eval_dims": {"manip": "spatial_pick_place", "cognition": "semantic"},
},
```

The `TASK_MAPPING` entry is not required by the current execution path, but it
keeps discovery and evaluation metadata complete.

## Validation

Run the static contract tests first:

```bash
cd source/geniesim_benchmark
PYTHONPATH=src pytest tests/test_stack_red_block_on_black_block_task.py -q
```

Then run the first headless preview:

```bash
geniesim benchmark run g2op_spatial_stack_red_block_on_black_block \
  --app.headless=true \
  --benchmark.preview=true \
  --benchmark.num_episode=1 \
  --benchmark.num_instances=1 \
  --benchmark.enable_vec=0 \
  --benchmark.record=false
```

Inspect the head and hand-camera previews and confirm:

- Exactly two blocks are present.
- The red block is red.
- The overridden block is visually black, not dark blue or red.
- Both blocks rest on the table and are reachable.
- The initial state is not already successful.

Finally, exercise four checker states in simulation: separated blocks, reversed
stack, insufficient overlap, and valid red-on-black placement.

### Instance 0 verification result

On 2026-07-20, instance `0` passed the following checks:

- The complete benchmark test suite passed.
- OpenUSD composed both real cube payloads and resolved the black visual mesh to
  the task-local black material under `/Workspace`.
- The G2 Omnipicker headless preview exited successfully and wrote head,
  left-hand, and right-hand camera images under `debug_preview/`.
- The rendered scene contains exactly one red cube and one black cube, separated
  on the table and visible to the policy cameras.
- The untouched initial state scored `Ontop = 0`.
- The existing `Ontop.update()` implementation passed controlled checks for
  adjacency, reversed order, insufficient overlap, and valid red-on-black
  placement.

## Generated 40-Scenario Suite

The task bundle contains deterministic instances `0` through `39`:

- `0`: baseline.
- `1-11`: red/black XY position and yaw changes.
- `12-17`: background changes.
- `18-25`: color-temperature and intensity changes.
- `26-29`: table-height changes.
- `30-39`: combined stress cases.

Every instance also contains `scenario.json`; the root
`scenario_manifest.json` records the seed and all sampled values. The original
task-specific generator has been removed. To create a new task-neutral
augmentation suite from instance `0`, run from the repository root:

```bash
python source/geniesim_benchmark/scripts/generate_task_scenarios.py \
  --task stack_red_block_on_black_block \
  --source-instance 0 \
  --profile source/geniesim_benchmark/scripts/scenario_augmentation.example.json \
  --count 40
```

The generic output is written to the sibling
`stack_red_block_on_black_block_augmented/` task by default and is not intended
to reproduce the historical hand-designed 30-standard/10-stress matrix above.

The generator keeps the following invariants:

- Red and black object IDs match across all four files in each instance.
- Both blocks use the same 5 cm geometry and mass.
- Initial center separation is at least 0.12 m.
- Both blocks remain inside the G2 reachable workspace.
- `Ontop` always uses red as active and black as passive.

Run and archive all 40 policy-camera previews with:

```bash
python source/geniesim_benchmark/src/geniesim_benchmark/scripts/preview_task_gallery.py \
  --output-dir task_previews/stack_red_block_on_black_block/final \
  --include stack_red_block_on_black_block \
  --num-instances 0 \
  --fail-fast
```

Build the labeled head-camera contact sheet with:

```bash
python source/geniesim_benchmark/scripts/build_stack_red_black_contact_sheet.py \
  --preview-dir task_previews/stack_red_block_on_black_block/final/g2op_spatial_stack_red_block_on_black_block \
  --manifest source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/stack_red_block_on_black_block/scenario_manifest.json \
  --output task_previews/stack_red_block_on_black_block/stack_red_black_40_contact_sheet.png
```

Passing `--benchmark.num_instances=0` evaluates every generated instance;
positive values retain the existing deterministic subset-sampling behavior.
