# Benchmark Run: g2op_robust_posegen_pick_block_color

This note records the two-terminal command sequence for evaluating
`g2op_robust_posegen_pick_block_color` with:

- inference service enabled
- Isaac Sim headless
- `--benchmark.record=true`

The benchmark runtime is `geniesim_benchmark`, launched through the
`geniesim benchmark` CLI.

## Terminal 1: Start Inference Service

Run the policy server on the host and keep this terminal open:

```bash
cd <ACOT_VLA_ROOT>
bash scripts/server.sh 0 8999 PI05_GENIE_SIM_INSTRUCTION_AND_ROBUST
```

Success marker:

```text
server listening on 0.0.0.0:8999
```

Notes:

- `0` is the GPU id.
- `8999` is the WebSocket inference port.
- `PI05_GENIE_SIM_INSTRUCTION_AND_ROBUST` is the instruction/robust benchmark
  environment enum used by the baseline service.

## Terminal 2: Start Isaac Sim Headless

From the Genie Sim repo root on the host:

```bash
cd <GENIE_SIM_REPO_ROOT>
geniesim docker up --headless
geniesim docker into
```

Inside the container:

```bash
export SIM_ASSETS=/geniesim_assets
export SIM_REPO_ROOT=/workspace
```

Optional but recommended inference probe:

```bash
/isaac-sim/python.sh -m geniesim_cli benchmark check-inference \
  --infer-host=127.0.0.1:8999
```

Expected result: `PASS`.

## Run The Benchmark

Inside the container:

```bash
/isaac-sim/python.sh -m geniesim_cli benchmark run g2op_robust_posegen_pick_block_color \
  --infer-host=127.0.0.1:8999 \
  --app.headless=true \
  --benchmark.record=true \
  --benchmark.num_episode=1
```

The task config defaults include:

- `model_arc: corobot`
- `num_episode: 1`
- `num_instances: 10`
- `record: false`, overridden above by `--benchmark.record=true`

## Outputs

With `SIM_REPO_ROOT=/workspace`, evaluation results are written under:

```text
/workspace/output/benchmark/table_task_1_g2_op_posegen/pick_block_color/
```

Expected files/directories include:

```text
evaluate_ret_00.json
recording_*/
```

## Stop

```bash
# Terminal 1
Ctrl+C

# Terminal 2, inside container
exit

# Host
geniesim docker down
```
