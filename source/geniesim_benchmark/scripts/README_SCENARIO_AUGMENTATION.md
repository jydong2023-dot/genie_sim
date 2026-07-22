# 通用 LLM-task 场景增广

`generate_task_scenarios.py` 从任意
`llm_task/<task>/<source-instance>` 场景生成确定性增广场景。`--task` 是必填参数，
工具不包含任何具体任务的场景矩阵、对象 ID 或资产定义。

纯增广核心已拆分为同级独立包
[`scene_augmentation`](../../scene_augmentation/README.md)。当前脚本是
GenieSim Benchmark 适配入口，负责默认任务目录、YAML 匹配和 Isaac Sim 预览；
独立核心命令使用显式 `--task-dir`，不依赖 Benchmark：

```bash
scene-augmentation \
  --task-dir /path/to/task \
  --source-instance 0 \
  --profile /path/to/profile.json \
  --count 10
```

## 快速开始

先查看自动识别的物体和桌子：

```bash
python scripts/generate_task_scenarios.py \
  --task stack_red_block_on_black_block \
  --source-instance 0 \
  --list-objects
```

用默认配置生成 40 个场景。输出直接写回原任务目录，因此原来的
`sub_task_name` 保持不变。默认先读取现有数字目录的最大编号，再从下一个编号
开始追加。例如已有 `0` 到 `39`，本次 40 个输出编号为 `40` 到 `79`：

```bash
python scripts/generate_task_scenarios.py \
  --task stack_red_block_on_black_block \
  --source-instance 0 \
  --count 40 \
  --seed 20260720
```

使用显式配置：

```bash
python scripts/generate_task_scenarios.py \
  --task stack_red_block_on_black_block \
  --source-instance 0 \
  --profile scripts/scenario_augmentation.example.json \
  --count 40
```

只有明确希望删除原任务中所有数字场景并从 `0` 重新生成时才使用
`--replace-generated`。源实例会先暂存，因此它可以安全地位于待替换目录内；
非数字文件不会被删除。

生成后默认调用匹配相同 `sub_task_name` 的 benchmark YAML，只预览本次新增的
精确实例编号。每个实例保存 `head.png`、`left_hand.png` 和 `right_hand.png`，并把
所有相机图拼到 `contact_sheet.png`。默认输出位置是
`<task>/previews/generated_<first>_<last>/<config-name>/`。如果一个任务尚无 YAML，
使用 `--preview-config <yaml>`；只需要生成、不运行 Isaac Sim 时使用
`--skip-preview`。

## 完整增广和预览：宿主机与容器运行方式

完整的“场景增广 + Isaac Sim 预览 + 拼图”应在 `geniesim3` 容器中运行。
场景增广本身可以在宿主机运行，但宿主机没有容器内完整的 Isaac Sim
`/workspace` 环境，因此宿主机运行时应使用 `--skip-preview`。

当前稳定运行时是 Isaac Sim 5.1，对应：

- CLI：`geniesim docker5.1`
- 镜像：`registry.agibot.com/genie-sim/geniesim3:latest`
- 容器：`geniesim3`
- 仓库挂载：`/home/user/djy/genie_sim -> /workspace`
- 资产挂载：`/home/user/djy/geniesim_assets -> /geniesim_assets`

请明确使用 `docker5.1`，不要使用尚未完成的 Isaac Sim 6.0 容器路径。

### 1. 宿主机准备

```bash
cd /home/user/djy/genie_sim

source /home/user/miniforge3/etc/profile.d/conda.sh
conda activate geniesim

export GENIESIM_REPO_ROOT=/home/user/djy/genie_sim
export GENIESIM_WORKSPACE=/home/user/djy/genie_sim
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets

test -f "$GENIESIM_WORKSPACE/docker/Dockerfile.5.1"
test -f "$GENIESIM_ASSETS_SRC/pyproject.toml"
nvidia-smi
```

### 2. 启动容器

先检查容器状态：

```bash
docker inspect -f '{{.State.Status}}' geniesim3
```

如果输出 `running`，不需要重复启动。如果容器不存在：

```bash
geniesim docker5.1 up --headless
```

如果容器存在但状态为 `exited`，先移除旧容器再启动：

```bash
geniesim docker5.1 down
geniesim docker5.1 up --headless
```

首次启动缺少镜像时，Docker 会自动拉取。也可以提前执行：

```bash
docker pull registry.agibot.com/genie-sim/geniesim3:latest
```

确认工作区和资产挂载：

```bash
docker inspect geniesim3 \
  --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

至少应看到：

```text
/home/user/djy/genie_sim -> /workspace
/home/user/djy/geniesim_assets -> /geniesim_assets
```

### 3. 检查容器运行环境

```bash
docker exec \
  -u "$(id -u):$(id -g)" \
  -e HOME=/home/isaac-sim \
  -w /workspace \
  geniesim3 \
  bash -lc '
    command -v geniesim
    command -v omni_python
    python3 -c "import yaml, PIL; print(\"system Python dependencies OK\")"
    omni_python -c "import geniesim_benchmark; print(\"Isaac Python dependencies OK\")"
    geniesim status
  '
```

必须使用宿主机 UID/GID 和 `HOME=/home/isaac-sim`。直接以 root 身份运行
`docker exec` 时，容器可能找不到安装在
`/home/isaac-sim/.local/bin/` 中的 `geniesim`。

### 4. 完整执行增广、预览和拼图

以下示例使用现有任务 `clean_the_desktop`。它与
`g2op_manip_clean_the_desktop.yaml` 中的 `sub_task_name` 一致：

```bash
docker exec -it \
  -u "$(id -u):$(id -g)" \
  -e HOME=/home/isaac-sim \
  -w /workspace/source/geniesim_benchmark \
  geniesim3 \
  bash -lc '
    python3 scripts/generate_task_scenarios.py \
      --task clean_the_desktop \
      --source-instance 0 \
      --profile scripts/scenario_augmentation.example.json \
      --count 4 \
      --seed 20260720
  '
```

该命令会依次执行：

1. 读取原任务目录中的最大数字编号并追加 4 个场景；
2. 保持 `sub_task_name=clean_the_desktop` 不变；
3. 自动找到匹配的 benchmark YAML；
4. 只加载并预览本次新增的精确实例编号；
5. 每个实例保存三个相机预览；
6. 把本次全部相机图合成为 `contact_sheet.png`。

如果自动找不到 YAML，可以显式指定：

```bash
--preview-config src/geniesim_benchmark/config/g2op_manip_clean_the_desktop.yaml
```

### 5. 输出位置

增广场景直接写回宿主机原任务目录：

```text
/home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/clean_the_desktop/
```

假设运行前最大编号是 `9`，本次 `--count 4` 会生成 `10` 到 `13`。预览目录为：

```text
clean_the_desktop/
└── previews/
    └── generated_10_13/
        └── g2op_manip_clean_the_desktop/
            ├── 10/
            │   ├── head.png
            │   ├── left_hand.png
            │   └── right_hand.png
            ├── 11/
            ├── 12/
            ├── 13/
            ├── metadata.json
            └── contact_sheet.png
```

在宿主机查找最新拼图：

```bash
find \
  /home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/clean_the_desktop/previews \
  -name contact_sheet.png \
  -printf '%T@ %p\n' | \
sort -nr | \
head -1
```

### 6. 替换模式

如果希望删除原任务中的所有数字场景，并从 `0` 重新生成：

```bash
docker exec -it \
  -u "$(id -u):$(id -g)" \
  -e HOME=/home/isaac-sim \
  -w /workspace/source/geniesim_benchmark \
  geniesim3 \
  bash -lc '
    python3 scripts/generate_task_scenarios.py \
      --task clean_the_desktop \
      --source-instance 0 \
      --profile scripts/scenario_augmentation.example.json \
      --count 4 \
      --seed 20260720 \
      --replace-generated
  '
```

源实例会在清理前暂存。该命令重新生成 `0` 到 `3`，并只预览这四个新场景；
任务目录中的非数字文件和非数字目录不会被删除。

### 7. 只增广、不运行 Isaac Sim 预览

只增广时可以直接在宿主机执行：

```bash
cd /home/user/djy/genie_sim/source/geniesim_benchmark

conda run -n geniesim python \
  scripts/generate_task_scenarios.py \
  --task clean_the_desktop \
  --source-instance 0 \
  --profile scripts/scenario_augmentation.example.json \
  --count 4 \
  --seed 20260720 \
  --skip-preview
```

### 8. 停止容器

任务结束后，场景和预览已经通过 bind mount 保存在宿主机。停止并删除容器：

```bash
cd /home/user/djy/genie_sim
source /home/user/miniforge3/etc/profile.d/conda.sh
conda activate geniesim
geniesim docker5.1 down
```

Isaac Sim 缓存仍保存在：

```text
/home/user/docker/isaac-sim/
```

## 支持的增广维度

| 维度 | 实现 |
|---|---|
| `object_pose` | 在指定 XY 范围随机采样位置和 yaw，并执行最小间距约束；同步更新 USD 和 `scene_info.json`。 |
| `lighting` | 将色温和强度写入 `scenario.json.light_config`；benchmark 加载时通过现有 `BaseEnv`/`APICore` 灯光路径应用到组合场景中的灯光。 |
| `table_height` | 同时提升/降低桌子及 `move_with_table_ids` 指定的桌上物体；同步元数据。 |
| `table_appearance` | 使用强于子层材质绑定的 `UsdPreviewSurface` 覆盖桌面颜色、粗糙度、金属度，可选复制并绑定纹理。 |
| `combined` | 在同一场景组合所有适用维度；无桌场景会自动跳过桌子相关变化。 |

本次新生成的第一个场景默认是 baseline，之后按照 `dimensions` 循环。设置
`"include_baseline": false` 可让所有输出都是增广场景。

## 配置注意事项

- 未指定 `object_pose.object_ids` 时，工具把 `scene_info.json.layout` 中所有非桌对象视为可移动物体。
- 未指定 `table_ids` 时，工具根据 object category、semantic name、keywords 和 ID 自动识别桌子。
- 示例 profile 中的 ID 列表默认为空，因此可直接用于任意任务；需要精确控制目标时，再把 `--list-objects` 的结果填入列表。
- 如果源场景的桌子属于背景 USD、没有出现在 `scene_info.json.layout`，工具会自动跳过 `table_height` 和 `table_appearance`，其他增广仍正常生成。
- 对复杂场景建议先运行 `--list-objects`，然后显式填写 ID，避免移动固定背景物体。
- 纹理路径相对于 profile JSON 所在目录解析；每个输出场景会复制到自己的 `augmentation_assets/`，因此输出目录可整体移动。
- 生成目录保留原始 `instructions.json`、`problems.json` 及其他文件。原始 USD 保存为 `scene_source.usda`，新的 `scene.usda` 只包含更强的覆盖意见。

配置结构可直接参考
[`scenario_augmentation.example.json`](scenario_augmentation.example.json)。新增增广维度时，在
`scene_augmentation/src/scene_augmentation/scenario_augmentation.py` 中扩展 profile
校验、采样和 USD/元数据渲染；Benchmark 脚本只维护预览适配。
