# Data Collection Saved Task Conversion

`convert_saved_tasks_to_benchmark.py` converts every saved-task JSON in one
data-collection directory into a numeric `llm_task` scene instance. It only
uses the Python standard library; Isaac Sim does not need to be running.

Each output instance contains:

- `scene.usda`: table and object payloads with converted local poses
- `scene_info.json`: object metadata and relation graph
- `instructions.json`: the benchmark instruction
- `problems.json`: `Follow` and `Upright` evaluation checkers

## Straighten Beverage Batch

Preview the source-to-instance mapping without writing files:

```bash
cd /home/user/djy/genie_sim/source/geniesim_benchmark

./scripts/convert_saved_tasks_to_benchmark.py \
  --input-dir /home/user/djy/genie_sim/source/data_collection/saved_task/straighten_and_place_beverage_g2 \
  --output-task-dir /home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/straighten_object \
  --source-template /home/user/djy/genie_sim/source/data_collection/tasks/geniesim_2025/straighten_object/straighten_beverage_g2.json \
  --assets-root /home/user/djy/geniesim_assets \
  --dry-run
```

Remove `--dry-run` to generate the scenes. The converter automatically starts
after the largest existing numeric instance. Use `--start-instance N` to choose
an explicit range. Existing instance directories are never overwritten unless
`--force` is also passed.

For the current repository, the five source files were generated as instances
50 through 54. Run only those scenes in the existing Docker container with:

```bash
/isaac-sim/kit/python/bin/geniesim benchmark run g2op_if_straighten_object.yaml \
  --app.headless=false \
  --benchmark.instance_ids=50,51,52,53,54 \
  --benchmark.num_episode=1 \
  --benchmark.record=false
```

`--benchmark.num_episode=1` means one rollout for each selected scene instance.
When `--benchmark.instance_ids` is present, it takes precedence over random
`--benchmark.num_instances` sampling.

## Conversion Semantics

- Source object poses are world-space. The converter applies the inverse pose
  of `origin` from `--source-template`, producing workspace-local benchmark
  poses.
- Source and USDA quaternions are WXYZ. `scene_info.json` is emitted as XYZW.
- Data collection loads each object's raw `Aligned.usd`, while benchmark scenes
  payload the `Aligned.usda` wrapper. The converter cancels the wrapper
  `entity` rotation at the parent so the composed rigid-body pose remains
  identical to the saved-task pose.
- Positive target local Y selects `left_gripper`; negative local Y selects
  `right_gripper`, matching the benchmark's current convention.
- The source upright threshold is in radians. It is converted to degrees for
  ADER's `Upright` checker. Use `--upright-threshold-deg` to override it.
- The source `is_gripper_in_view` filter has no equivalent ADER checker. It is
  omitted and reported in the generated conversion manifest.
- The default table pose and asset match `home_b_with_table`. For another task,
  set `--table-asset`, `--table-local-position`, and
  `--table-local-quaternion` explicitly.
