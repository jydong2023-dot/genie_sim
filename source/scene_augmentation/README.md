# scene_augmentation

Standalone deterministic augmentation for GenieSim-compatible task bundles.
The core package reads and writes scene files only; it does not import
`geniesim_benchmark`, launch Isaac Sim, or assume a repository layout.

```bash
pip install -e /home/user/djy/genie_sim/source/scene_augmentation

scene-augmentation \
  --task-dir /path/to/llm_task/my_task \
  --source-instance 0 \
  --profile profile.json \
  --count 10
```

Supported dimensions are `object_pose`, `lighting`, `table_height`,
`table_appearance`, and `combined`. Lighting parameters are stored in
`scenario.json`; applying them is the responsibility of the consuming runtime.

GenieSim Benchmark integration—including YAML lookup, exact-instance preview,
camera archival, and Isaac Sim launch—remains in `geniesim_benchmark`.

The packaged default profile is
`src/scene_augmentation/profiles/default.json`. The historical Benchmark
script remains as a compatibility and preview-adapter entry point.
