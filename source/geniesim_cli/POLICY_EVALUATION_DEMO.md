# Policy Evaluation 双终端启动指南

本文档说明如何在 **两个终端** 中启动本地 policy evaluation（以 baseline `g2op_if_pick_block_color` + ACoT-VLA π₀.₅ 为例）。

## 架构

```
终端 1（host）                    终端 2（host → geniesim3 容器）
ACoT-VLA serve_policy :8999  ←→  geniesim benchmark run（Isaac Sim）
         WebSocket corobot 协议
```

容器使用 `network_mode: host`，容器内访问推理服务用 `127.0.0.1:8999`。

## 前置条件

| 项目 | 说明 |
|------|------|
| GPU / 驱动 | `nvidia-smi` 正常 |
| Conda | `conda activate geniesim` |
| 仿真镜像 | `registry.agibot.com/genie-sim/geniesim3:latest` 已构建 |
| 资产 | `pip install -e /path/to/geniesim_assets` |
| Benchmark 包 | `pip install -e source/geniesim_benchmark` |
| ACoT-VLA | 代码、依赖、`instruction_and_robust_pi05` checkpoint 已就绪（见 `/home/user/djy/ACoT-VLA/README.md`） |

---

## 终端 1：启动 Baseline 推理服务（host）

**保持此终端运行，不要关闭。**

```bash
cd /home/user/djy/ACoT-VLA

bash scripts/server.sh 0 8999 PI05_GENIE_SIM_INSTRUCTION_AND_ROBUST
```

成功标志：

```
Finished restoring checkpoint from .../checkpoints/instruction_and_robust_pi05/params
Loaded norm stats from .../checkpoints/instruction_and_robust_pi05/assets
server listening on 0.0.0.0:8999
```

说明：

- `0` = GPU 编号（`CUDA_VISIBLE_DEVICES`）
- `8999` = WebSocket 端口
- `PI05_GENIE_SIM_INSTRUCTION_AND_ROBUST` = instruction/robust 榜单 env 枚举名（必须大写）

---

## 终端 2：启动仿真并跑 Benchmark

### 2.1 探活推理服务（host，可选但推荐）

```bash
conda activate geniesim

geniesim benchmark check-inference --infer-host=127.0.0.1:8999
```

期望输出：`✅ PASS`。

### 2.2 启动并进入 GenieSim 容器

```bash
cd /home/user/djy/genie_sim

# 无 GUI / 远程环境
geniesim docker up --headless

# 进入容器 shell
geniesim docker into
```

重启后容器不会自动运行，需先 `docker up` 再 `into`。

### 2.3 容器内：再次探活（可选）

```bash
export SIM_ASSETS=/geniesim_assets
export SIM_REPO_ROOT=/workspace

/isaac-sim/python.sh -m geniesim_cli benchmark check-inference --infer-host=127.0.0.1:8999
```

### 2.4 容器内：运行评测

**单 episode 快速验证：**

```bash
/isaac-sim/python.sh -m geniesim_cli benchmark run g2op_if_pick_block_color \
  --infer-host=127.0.0.1:8999 \
  --app.headless=true \
  --benchmark.record=true \
  --benchmark.num_episode=1
```

**多 episode 评测（示例 10 轮）：**

```bash
/isaac-sim/python.sh -m geniesim_cli benchmark run g2op_if_pick_block_color \
  --infer-host=127.0.0.1:8999 \
  --app.headless=true \
  --benchmark.record=true \
  --benchmark.num_episode=10 \
  --benchmark.seed=0
```

### 2.5 正常运行时的日志特征

仿真终端应出现：

- `CoRobotPolicy: calling model infer`
- `Sending payload to server, size=...`
- `[Physics Callback] ~95–100 Hz`
- `Evaluation result file generated at .../evaluate_ret_00.json`

推理终端应出现：

- `connection open`
- `Policy infering for task: pick_block_color, with inference time: ... ms`

---

## 输出路径

评测结果与录制（容器内，通常 bind 到 workspace）：

```
/workspace/output/benchmark/table_task_1_g2_op/pick_block_color/
├── evaluate_ret_00.json       # 汇总分数
└── recording_000*/            # 各 episode 录制（若 --benchmark.record=true）
```

---

## 停止服务

```bash
# 终端 1：Ctrl+C 停止推理服务

# 终端 2：容器内 exit 退出 shell
exit

# host 上停止并删除仿真容器
geniesim docker down
```

---

## 常见问题

| 问题 | 处理 |
|------|------|
| `Driver/library version mismatch` | 重启使 NVIDIA 驱动与内核模块版本一致 |
| `check-inference` 连接 refused | 确认终端 1 推理服务已启动且监听 8999 |
| 容器内连不上 8999 | 确认容器为 host 网络；地址用 `127.0.0.1:8999` |
| `--env` 参数 invalid choice | 使用枚举名如 `PI05_GENIE_SIM_INSTRUCTION_AND_ROBUST`，非小写 |

## 相关文档

- Benchmark 任务说明：`source/geniesim_benchmark/USAGE.md`
- ACoT-VLA baseline：`/home/user/djy/ACoT-VLA/README.md`
- 数据采集 demo：`source/data_collection/DATA_COLLECTION_DEMO.md`
