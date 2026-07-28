# scene_augmentation

`scene_augmentation` 是独立的确定性场景增广包，负责读取和生成兼容
GenieSim task bundle 的场景文件。核心包不导入 `geniesim_benchmark`，不启动
Isaac Sim，也不假设任务必须位于 GenieSim 仓库中。

支持的增广维度：

- `object_pose`：物体位置与 yaw；
- `lighting`：光照色温与强度参数；
- `table_height`：桌面及桌上物体高度；
- `table_appearance`：桌面颜色、粗糙度、金属度和纹理；
- `combined`：组合所有对当前场景适用的维度。

## 安装

所有 Python 指令统一使用 `python3`：

```bash
cd /home/user/djy/genie_sim

python3 -m pip install -e source/scene_augmentation
```

确认模块与命令入口可用：

```bash
python3 -c "import scene_augmentation; print(scene_augmentation.__file__)"
python3 -m scene_augmentation.cli --help
```

## 独立执行场景增广

独立 CLI 必须通过 `--task-dir` 接收明确的任务目录，不会自动查找
`geniesim_benchmark`：

```bash
python3 -m scene_augmentation.cli \
  --task-dir /path/to/llm_task/my_task \
  --source-instance 0 \
  --profile /path/to/profile.json \
  --count 10 \
  --seed 20260720
```

例如增广 GenieSim Benchmark 中的任务，但不启动预览：

```bash
cd /home/user/djy/genie_sim

python3 -m scene_augmentation.cli \
  --task-dir source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/clean_the_desktop \
  --source-instance 0 \
  --profile source/scene_augmentation/src/scene_augmentation/profiles/default.json \
  --count 4 \
  --seed 20260720
```

默认读取任务目录中现有数字文件夹的最大编号，从下一个编号开始追加。只有明确
需要删除原数字场景并从 `0` 重新生成时才使用：

```bash
python3 -m scene_augmentation.cli \
  --task-dir /path/to/llm_task/my_task \
  --source-instance 0 \
  --profile /path/to/profile.json \
  --count 10 \
  --seed 20260720 \
  --replace-generated
```

查看场景中自动识别的可移动物体和桌子，不写入文件：

```bash
python3 -m scene_augmentation.cli \
  --task-dir /path/to/llm_task/my_task \
  --source-instance 0 \
  --profile /path/to/profile.json \
  --list-objects
```

包内默认 profile 位于：

```text
source/scene_augmentation/src/scene_augmentation/profiles/default.json
```

光照参数保存在每个实例的 `scenario.json` 中。独立核心只负责生成参数，具体
模拟器需要实现相应的运行时应用逻辑。

## Isaac Sim Preview 必须在容器中运行

`scene_augmentation` 核心包不直接启动 Isaac Sim。GenieSim 的 YAML 匹配、
精确实例选择、三个相机预览、图片归档和拼图由 `geniesim_benchmark` 适配器完成。

完整的“场景增广 + Isaac Sim preview + contact sheet”必须在带有 Isaac Sim 5.1
的 `geniesim3` 容器中运行。不要在宿主机直接启动 preview。

### 1. 在宿主机启动容器

```bash
cd /home/user/djy/genie_sim

source /home/user/miniforge3/etc/profile.d/conda.sh
conda activate geniesim

export GENIESIM_REPO_ROOT=/home/user/djy/genie_sim
export GENIESIM_WORKSPACE=/home/user/djy/genie_sim
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets

geniesim docker5.1 up --headless
```

如果 `geniesim3` 已经处于 `running` 状态，不需要重复启动：

```bash
docker inspect -f '{{.State.Status}}' geniesim3
```

如果存在已停止的旧容器：

```bash
geniesim docker5.1 down
geniesim docker5.1 up --headless
```

### 2. 在容器中运行增广和 Preview

从宿主机执行下面的 `docker exec`。容器内部的代码指令使用 `python3`：

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
      --profile ../scene_augmentation/src/scene_augmentation/profiles/default.json \
      --count 4 \
      --seed 20260720
  '
```

这里调用的是 Benchmark 预览适配入口。它内部使用 `scene_augmentation` 核心完成
增广，然后自动：

1. 查找与任务 `sub_task_name` 匹配的 Benchmark YAML；
2. 只预览本次新增的实例编号；
3. 保存 `head.png`、`left_hand.png` 和 `right_hand.png`；
4. 生成包含全部实例和相机画面的 `contact_sheet.png`。

### 3. 输出目录

场景和预览通过 `/workspace` bind mount 直接写回宿主机。例如：

```text
/home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/clean_the_desktop/
├── <new-instance-id>/
│   ├── scene.usda
│   ├── scene_source.usda
│   ├── scene_info.json
│   └── scenario.json
├── scenario_manifest.json
└── previews/
    └── generated_<first>_<last>/
        └── g2op_manip_clean_the_desktop/
            ├── <instance-id>/
            │   ├── head.png
            │   ├── left_hand.png
            │   └── right_hand.png
            ├── metadata.json
            └── contact_sheet.png
```

### 4. 停止容器

```bash
cd /home/user/djy/genie_sim
source /home/user/miniforge3/etc/profile.d/conda.sh
conda activate geniesim
geniesim docker5.1 down
```

停止容器不会删除已经写回宿主机的场景、预览图和
`/home/user/docker/isaac-sim/` 缓存。
