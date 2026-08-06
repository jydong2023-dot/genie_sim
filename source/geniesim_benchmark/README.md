# geniesim_benchmark — Benchmark tasks, scoring, LLM eval 🧪

Declarative task configs + a runtime that loads a scene, drives a
robot, evaluates a policy, and records scores. The canonical entry is
the `geniesim benchmark` CLI verb (owned by
[`geniesim_cli`](../geniesim_cli/)).

License: [Mozilla Public License Version 2.0](LICENSE)
Agent doc: see [`../../.agent/geniesim_benchmark.md`](../../.agent/geniesim_benchmark.md)
Skills: [`skills/`](skills/)

---

## 📦 Install

```bash
pip install -e source/geniesim_benchmark/
```

Pulled in automatically by `geniesim bootstrap`. Heavy runtime deps
(Isaac Sim, MuJoCo, open3d, …) come from this package.

---

## 🛠️ What you can do

### Run a task against an inference server

```bash
geniesim benchmark run g2op_if_pick_block_color \
  --infer-host=<IP>:8999
```

### Probe an inference server before sinking minutes into a sim launch

```bash
geniesim benchmark check-inference \
  --infer-host=<IP>:8999 --arch=corobot
```

### Discover tasks

```bash
geniesim benchmark categories         # show category counts
geniesim benchmark robots             # show robot counts
geniesim benchmark list --robot=g2op --category=instruction_following
```

### Batch-evaluate a sweep

```bash
geniesim benchmark batch --category=instruction_following --robot=g2op
```

### Augment one LLM-task scene

Generate deterministic variants of any numeric scene bundle under
`benchmark/config/llm_task/`. The tool supports object pose, benchmark-runtime
lighting, table height, and table color/texture changes while preserving the
source task's instructions and scoring rules:

```bash
python scripts/generate_task_scenarios.py \
  --task stack_red_block_on_black_block \
  --source-instance 0 \
  --count 40
```

The command appends after the task's highest numeric instance, previews exactly
the new instances, and writes per-camera images plus a contact sheet. Pass
`--replace-generated` to replace numeric instances from zero, or
`--skip-preview` when Isaac Sim preview is not needed.

Use `--list-objects` before writing a profile for a complex scene. See the
[scenario augmentation guide](scripts/README_SCENARIO_AUGMENTATION.md) and
[example profile](scripts/scenario_augmentation.example.json).

For `g2_op_pick_toy`, `blue_block` is part of the background USD instead of the
task's `/Workspace` layer. Generate its collision-checked XY + yaw variants with
the existing OpenUSD bindings in the `geniesim` environment:

```bash
conda run -n geniesim python \
  scripts/generate_g2_op_pick_toy_pose_variants.py \
  --count 10 \
  --seed 20260805
```

This preserves baseline instance `0`, writes task instances `1-10`, and writes
their background wrappers under
`geniesim_assets/background/olalab/g2_op_pick_toy_pose_variants/`. Run only the
randomized instances with:

```bash
geniesim benchmark run g2op_robust_g2_op_pick_toy_posegen.yaml
```

### Adapt an existing USD scene for benchmark debugging

Generate a runnable benchmark YAML and eval-task JSON from a USD already stored
under `geniesim_assets`. This loads the scene, robot, and configured cameras; it
does not invent target-object physics or success scoring:

```bash
GENIESIM_ASSETS_ROOT=/path/to/geniesim_assets
python scripts/adapt_usd_scene.py \
  --scene-usd "$GENIESIM_ASSETS_ROOT/background/robosnap/auto_usd/pick_plastic_bowl.usd" \
  --robot-id dual_agx_nero \
  --robot-cfg dual_agx_nero.json
```

Run the same script inside the GenieSim container with the mounted scene path
`/geniesim_assets/...`. Use `--dry-run` to inspect both documents and `--force`
only when an existing generated pair should be replaced. The command prints the
exact `geniesim benchmark run ...` command after writing the files.

### Convert collected datasets between formats

The benchmark stack ships dataset utilities under
`geniesim_benchmark.dataset.*`. The first converter goes from
**agibot v1 → LeRobot v2.1** (parquet + HEVC/PNG-encoded MP4s):

```bash
geniesim dataset convert agibot-to-lerobot \
  --agibot-dir ./agibot \
  --output-dir ./lerobot_out
```

The `--agibot-dir` argument accepts either a single-episode dir
(contains `aligned_joints.h5` directly) or a parent dir of multiple
episode subdirs — auto-detected at runtime. Pass
`--lerobot-ref-dir <path>` to fill missing fisheye / head_back
extrinsic columns from a reference dataset; omit it to leave those
columns empty. Requires **ffmpeg on `PATH`** (RGB → HEVC, depth → PNG).

---

## 🤖 Skills

| Skill | Purpose |
|---|---|
| [run-benchmark](skills/run-benchmark/SKILL.md) | Launch a benchmark task locally against a user-provided inference server |
| [check-inference](skills/check-inference/SKILL.md) | Probe a model inference WebSocket server and validate the response |

---

## 📂 Layout

```
src/geniesim_benchmark/
├── app/app.py            # runtime entry, called by `geniesim benchmark run`
├── config/               # *.yaml task configs (the work-list)
├── dataset/              # dataset utilities (format conversion, …)
│   └── convert/
│       └── agibot_to_lerobot.py   # public convert_agibot_to_lerobot() + convert_cli()
└── …
```

`config/*.yaml` is the source of truth for what's a benchmark task —
robot, scene, policy, scoring rule. The runtime is config-driven; new
tasks land as new yaml files, not new code.

`dataset/` is the home for off-line data utilities (format converters,
schema inspectors). Each converter exposes a plain-Python API plus a
`convert_cli(argv)` wrapper used by the `geniesim dataset convert …`
dispatcher — `argparse` only lives in the wrapper, the API is usable
from notebooks.

---

## 🔗 Pointers

- 🗺️ Module map: [`../README.md`](../README.md)
- 🏠 Repo root: [`../../README.md`](../../README.md)
- 🤖 Agent dispatcher: [`../../.agent/geniesim_benchmark.md`](../../.agent/geniesim_benchmark.md)
- 🏆 Leaderboard / public scores: [`../../README.md`](../../README.md) § Genie Sim Benchmark Leaderboard
