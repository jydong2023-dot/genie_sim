# 从 saved task 生成到 benchmark 场景加载

本文以 `straighten_and_place_beverage_g2` 为例，串联以下流程：

1. 只生成 data collection 的布局 JSON，不采集轨迹；
2. 批量转换成 `geniesim_benchmark` 可读取的 `llm_task` 实例；
3. 在 Isaac Sim GUI 中加载场景和 G2OP 机器人，不启动 policy 推理；
4. 可选：使用同一批实例运行正式 benchmark。

仓库中的实际目录名是 `llm_task`，不是 `llm_tasks`。

## 路径与运行环境

| 内容 | 宿主机路径 | 容器内路径 |
|---|---|---|
| data collection | `/home/user/djy/genie_sim/source/data_collection` | `/geniesim/main/data_collection` |
| benchmark | `/home/user/djy/genie_sim/source/geniesim_benchmark` | `/workspace/source/geniesim_benchmark` |
| assets | `/home/user/djy/geniesim_assets` | `/geniesim_assets` |

布局生成使用 `data_collection_open_source` 容器。Isaac Sim 场景检查和正式评测
使用现成的 `geniesim3` benchmark 容器。下面的流程不安装 Isaac Sim、Torch
或其他 Python 包。

## 1. 生成 saved task JSON

启动 data collection 容器后，在容器中执行：

```bash
export SIM_ASSETS=/geniesim_assets
cd /geniesim/main/data_collection

/isaac-sim/python.sh scripts/generate_layout.py \
  --layout-only \
  --task-template tasks/geniesim_2025/straighten_object/straighten_beverage_g2.json \
  --output-dir /geniesim/main/data_collection/saved_task \
  --num-episodes 5
```

`--layout-only` 只调用 `TaskGenerator.generate()`，不会连接 gRPC、启动运动
规划、采集轨迹或生成 MCAP。模板顶层的 `task` 为
`straighten_and_place_beverage_g2`，所以输出为：

```text
saved_task/straighten_and_place_beverage_g2/
├── straighten_and_place_beverage_g2_0.json
├── straighten_and_place_beverage_g2_1.json
├── straighten_and_place_beverage_g2_2.json
├── straighten_and_place_beverage_g2_3.json
└── straighten_and_place_beverage_g2_4.json
```

脚本不会覆盖已有的任务目录。如果该目录已经存在：

- 仅复用并检查已有 JSON 时，添加 `--skip-generate`；
- 重新随机生成时，先把原目录移动到备份位置，或者换一个
  `--output-dir`。生成脚本没有 `--force` 参数。

可用以下命令确认文件：

```bash
find saved_task/straighten_and_place_beverage_g2 \
  -maxdepth 1 -name '*.json' -type f
```

## 2. 转换为 benchmark llm_task

转换脚本只使用 Python 标准库，可以直接在宿主机运行，不需要启动 Isaac
Sim。先执行 dry run，确认输入文件和待分配的实例编号：

```bash
cd /home/user/djy/genie_sim/source/geniesim_benchmark

./scripts/convert_saved_tasks_to_benchmark.py \
  --input-dir /home/user/djy/genie_sim/source/data_collection/saved_task/straighten_and_place_beverage_g2 \
  --output-task-dir /home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/straighten_object \
  --source-template /home/user/djy/genie_sim/source/data_collection/tasks/geniesim_2025/straighten_object/straighten_beverage_g2.json \
  --assets-root /home/user/djy/geniesim_assets \
  --dry-run
```

确认映射无误后，去掉最后的 `--dry-run` 再运行一次。脚本默认从目标目录
中最大的数字实例之后开始分配，不覆盖已有实例。需要固定编号时可添加
`--start-instance N`；只有明确要替换已有结果时才同时使用 `--force`。

每个输出实例包含：

```text
llm_task/straighten_object/<instance_id>/
├── scene.usda
├── scene_info.json
├── instructions.json
└── problems.json
```

转换完成后还会在 `straighten_object/` 下生成
`conversion_manifest_<first>_<last>.json`。manifest 记录源 JSON、目标实例编号、
目标物体、左右手选择和不支持的 data collection filter，可据此确定下一步
要加载的 `instance_id`。

转换器会完成以下格式适配：

- 将 data collection 世界坐标转换为 benchmark 工作空间局部坐标；
- 将 USD 的 WXYZ 四元数转换为 `scene_info.json` 使用的 XYZW；
- 补偿 `Aligned.usda` wrapper 的 `entity` 旋转，保持物体最终姿态一致；
- 生成 `Follow` 和 `Upright` benchmark checker；
- 根据目标物体局部 Y 坐标选择 `left_gripper` 或 `right_gripper`。

## 3. 在 Isaac Sim 中加载，不运行 policy

先确认 benchmark 容器 `geniesim3` 正在运行。然后在宿主机执行：

```bash
cd /home/user/djy/genie_sim/source/geniesim_benchmark

GENIESIM_CONTAINER=geniesim3 ./scripts/open_benchmark_scene.bash \
  --config g2op_if_straighten_object \
  --instance-id 50
```

将 `50` 替换成 conversion manifest 中的实际实例编号。该入口会加载：

- `llm_task/straighten_object/<instance_id>/scene.usda`；
- YAML 配置指定的工作空间；
- `g2op_if_straighten_object.yaml` 指定的 G2OP 机器人。

它不会创建 policy 客户端，也不要求推理服务。Isaac Sim 会持续运行，直到
关闭窗口或在终端按 `Ctrl-C`。只验证路径解析而不启动 Isaac Sim 时添加
`--dry-run`。

也可以进入 `geniesim3` 容器后直接执行：

```bash
/workspace/source/geniesim_benchmark/scripts/open_benchmark_scene.bash \
  --config g2op_if_straighten_object \
  --instance-id 50
```

## 4. 可选：正式运行 benchmark

正式评测需要 YAML 中配置的 policy 服务已经启动。在 `geniesim3` 容器中
执行，例如当前已生成的 50 至 54 号实例：

```bash
cd /workspace/source/geniesim_benchmark

/isaac-sim/kit/python/bin/geniesim benchmark run \
  g2op_if_straighten_object.yaml \
  --app.headless=false \
  --benchmark.instance_ids=50,51,52,53,54 \
  --benchmark.num_episode=1 \
  --benchmark.record=false
```

`--benchmark.num_episode=1` 表示每个选中的场景实例执行一次 rollout。
`--benchmark.instance_ids` 会优先于随机的 `--benchmark.num_instances` 采样。

## 数据流

```text
straighten_beverage_g2.json
  -> TaskGenerator.generate()
  -> saved_task/straighten_and_place_beverage_g2/*.json
  -> convert_saved_tasks_to_benchmark.py
  -> benchmark/config/llm_task/straighten_object/<id>/{scene.usda,*.json}
  -> open_benchmark_scene.bash（仅加载）
  -> geniesim benchmark run（可选正式评测）
```

更详细的布局预览和 gRPC 双终端用法见
[README_LAYOUT_PREVIEW.md](README_LAYOUT_PREVIEW.md)。转换字段语义见
`../geniesim_benchmark/scripts/README_SAVED_TASK_CONVERSION.md`。
