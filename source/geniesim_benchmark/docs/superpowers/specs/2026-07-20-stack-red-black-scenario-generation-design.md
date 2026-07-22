# Red-on-Black Scenario Generation Design

## Goal

Extend `stack_red_block_on_black_block` from one benchmark scene to 40 fixed,
reproducible scenes. The suite must support both attributable, single-dimension
generalization measurements and a combined stress test while preserving the
ordered success condition `Ontop(red_block_000, black_block_000)`.

The generated scenes and their metadata are repository artifacts. A run with
the same generator seed must reproduce byte-identical outputs. The default root
seed is `20260720`.

## Scenario Matrix

The numeric instance IDs have stable meanings:

| IDs | Count | Split | Changed dimensions |
|---|---:|---|---|
| `0` | 1 | standard/baseline | Existing verified scene |
| `1-11` | 11 | standard/object_pose | Red/black XY position and yaw |
| `12-17` | 6 | standard/background | Background only |
| `18-25` | 8 | standard/lighting | Light temperature and intensity only |
| `26-29` | 4 | standard/table_height | Table and both blocks move together in Z |
| `30-39` | 10 | stress/combined | Pose, background, lighting, and table height |

Object centers are sampled within `x=[-0.20, 0.12] m` and
`y=[-0.22, 0.22] m`; yaw is sampled within `[-30, 30]` degrees. Cube centers
must be separated by at least `0.12 m`, remain on the tabletop, and not satisfy
`Ontop` at reset. Object yaw changes do not affect task semantics.

Table-height offsets are `-0.05`, `-0.025`, `0.025`, and `0.05 m` relative to
instance 0. The table and both cube center heights receive the same offset so
physics starts without penetration or floating objects.

Lighting uses the repository's supported light-generalization interface.
Temperature is selected from `3000`, `5000`, `7000`, and `9000 K`; intensity is
selected from `500`, `1000`, `3000`, and `6000`.

Backgrounds come from this explicit asset-relative candidate allowlist:

```text
background/room/room_3/background.usda
background/room/room_2/background.usda
background/home/home_b_aligned/background.usda
background/laboratory/laboratory_2/background.usda
background/study_room/study_4/background.usda
background/kitchen/kitchen_1/background.usda
background/warehouse/warehouse_1/background.usda
```

These paths are already used by G2 benchmark configurations in this checkout.
The first path is the baseline and the remaining six are the background-only
variants. Each must also successfully load with the G2 Omnipicker and the
task-local table. A background is accepted only after USD composition and
preview validation; an asset merely existing on disk is not enough. If a
candidate fails that validation, implementation stops and reports the path
instead of silently substituting another background and changing the fixed
suite.

## Generated Files

Add a benchmark-local generator script:

```text
scripts/generate_stack_red_black_scenarios.py
```

It writes instances under:

```text
src/geniesim_benchmark/benchmark/config/llm_task/
  stack_red_block_on_black_block/<instance_id>/
```

Every instance contains:

```text
scene.usda
scene_info.json
instructions.json
problems.json
scenario.json
```

The task directory also contains `scenario_manifest.json`, which records the
generator version, root seed, scenario count, split, dimension, and parameters
for every instance.

The script uses structured JSON serialization and generates USDA from a single
owned template. It does not edit arbitrary USDA text in place. By default it
refuses to overwrite an unexpected task directory. An explicit replacement
flag may replace only numeric instance directories and the generated manifest;
it must not delete unrelated files.

Instance 0 retains its verified geometry, instruction, problem, and material
contract. Its generated `scenario.json` and manifest entry describe it as the
baseline.

## Runtime Integration

Add a small scenario-config loader at the benchmark boundary. Before loading an
instance, `TaskBenchmark` resolves its `scenario.json`:

1. Select the instance-specific background USD before initializing the stage.
2. Create the environment using the existing task scene and subscene paths.
3. Store the fixed light configuration on the environment.
4. Apply it through the existing `BaseEnv.apply_generalization()` path.

Object poses and table height need no runtime mutation because they are authored
in each instance's `scene.usda`.

Instances without `scenario.json` retain current behavior. The feature must not
change other benchmark tasks.

The current vectorized benchmark path clones a single background across all
slots. A vectorized batch containing different instance backgrounds must fail
with an actionable error rather than silently use the wrong background. Serial
evaluation remains the supported path for the full 40-scene suite. Homogeneous
background vector batches may continue to work.

## Evaluation and Reporting

The existing scoring contract is unchanged. Each instance uses the same
instruction and ordered ADER leaf:

```json
{"Ontop": "red_block_000|black_block_000"}
```

The manifest provides stable grouping keys so evaluation results can be
aggregated as:

- baseline;
- object-pose generalization;
- background generalization;
- lighting generalization;
- table-height generalization;
- combined stress test;
- complete 40-scene suite.

`--benchmark.num_instances` continues to select a deterministic subset by run
seed. The default value `0` evaluates all 40 numeric directories.

## Preview Artifact

After generation, run headless preview validation and produce a contact-sheet
image for manual inspection. The contact sheet contains one labeled thumbnail
per instance, ordered `0-39`, and is written outside the task runtime bundle:

```text
task_previews/stack_red_block_on_black_block/contact_sheet.png
```

Labels include instance ID and scenario dimension. Individual rendered frames
remain in the preview output directory for closer inspection. The contact sheet
must make cube colors, placement, table height, background, and gross lighting
differences visible. A nonblank-image check and expected tile-count check run
before reporting the preview as successful.

## Validation

Offline tests verify:

- exactly 40 numeric instance directories exist;
- repeated generation with the same seed is byte-identical;
- every directory has the five required files;
- manifest and per-instance metadata agree;
- cube IDs, assets, colors, instructions, and ordered checker remain unchanged;
- cube positions remain in bounds and at least `0.12 m` apart;
- table and cube Z offsets move together;
- standard instances change only their declared dimension;
- stress instances vary all four requested dimensions;
- scenario runtime loading is backward compatible;
- mixed-background vector evaluation is rejected explicitly.

Simulator validation verifies all USD layers compose with real assets, all 40
scenes initialize without immediate success or fallen objects, and previews
render successfully. Manual inspection uses the generated contact sheet.

## Scope Boundaries

This change does not alter `Ontop`, robot initialization, object geometry,
object mass, black-material binding, policy inference, or unrelated benchmark
tasks. Camera perturbation, distractor objects, physics randomization, and
language paraphrases are useful future dimensions but are excluded from this
40-scene first version so the requested dimensions remain attributable.
