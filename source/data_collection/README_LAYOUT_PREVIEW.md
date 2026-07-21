# 布局生成与 Isaac Sim 预览

本文档说明如何调用 `client/layout` 生成随机布局，并将场景加载到 Isaac
Sim GUI 中预览。该流程不采集轨迹、不录制数据、不执行运动规划，也不会由
预览脚本启动或关闭 Isaac Sim 服务。

## 运行环境

服务端和预览脚本都在同一个 data-collection Docker 容器中运行，并统一使用
Isaac Sim 自带的 Python：

```text
/isaac-sim/python.sh
```

不要为下面的命令激活宿主机的 `base`、`geniesim` 或 `data_collect` conda
环境。`data_collector_server.py` 会导入 `isaacsim`，普通宿主机 Python 无法
替代 Isaac Sim Python。

本文命令使用当前机器上的以下路径：

- 仓库：`/home/user/djy/genie_sim`
- 资产：`/home/user/djy/geniesim_assets`
- 容器：`data_collection_open_source`
- 容器内仓库：`/geniesim/main/data_collection`
- 容器内资产：`/geniesim_assets`

需要提前准备 Docker、NVIDIA Container Toolkit 和 data-collection 镜像：

```text
registry.agibot.com/genie-sim/geniesim3-data-collection:latest
```

如果镜像尚未构建，在配置了 `geniesim` CLI 的宿主机环境中执行：

```bash
cd /home/user/djy/genie_sim/source/data_collection
geniesim autocollect build
```

## 终端 1：创建容器并启动 Isaac Sim 服务

先在宿主机终端执行：

```bash
export GENIE_SIM_ROOT=/home/user/djy/genie_sim
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets
cd "$GENIE_SIM_ROOT/source/data_collection"
./scripts/start_gui.sh run data_collection_open_source
```

该命令创建 GUI 容器并进入容器 shell。不要关闭这个终端。进入容器后，在
同一个终端继续执行：

```bash
export SIM_ASSETS=/geniesim_assets
cd /geniesim/main/data_collection
/isaac-sim/python.sh scripts/data_collector_server.py --enable_physics
```

预览只需要 `--enable_physics`。不要添加 `--enable_curobo` 或
`--publish_ros`，因为本流程不进行运动规划、ROS 发布或轨迹录制。

等待 Isaac Sim 窗口打开且 gRPC 服务启动完成后，再执行终端 2 的命令。

## 终端 2：生成布局并加载预览

打开另一个宿主机终端，执行以下完整命令。它会进入终端 1 已启动的同一个
容器，生成两个随机布局，并依次加载到 Isaac Sim GUI：

```bash
docker exec -it data_collection_open_source bash -lc '
  export SIM_ASSETS=/geniesim_assets
  cd /geniesim/main/data_collection
  /isaac-sim/python.sh scripts/preview_layout.py --gui \
    --task-template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json \
    --output-dir /geniesim/main/data_collection/layout_preview_output_run1 \
    --num-episodes 2
'
```

每个布局加载完成后，在终端 2 按 Enter，脚本会继续加载下一个布局。预览
结束后脚本只关闭本地 gRPC channel，不会关闭终端 1 中的 Isaac Sim 服务。

## 输出位置

生成结果位于容器内：

```text
/geniesim/main/data_collection/layout_preview_output_run1
```

由于仓库目录已挂载到容器中，同一结果可在宿主机直接访问：

```text
/home/user/djy/genie_sim/source/data_collection/layout_preview_output_run1
```

生成过程不会覆盖已有的任务输出目录。再次随机生成时，请修改
`--output-dir`，例如改为 `layout_preview_output_run2`。

## 重新加载已有布局

如需跳过随机生成并重新预览 `layout_preview_output_run1`，执行：

```bash
docker exec -it data_collection_open_source bash -lc '
  export SIM_ASSETS=/geniesim_assets
  cd /geniesim/main/data_collection
  /isaac-sim/python.sh scripts/preview_layout.py --gui \
    --task-template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json \
    --output-dir /geniesim/main/data_collection/layout_preview_output_run1 \
    --skip-generate
'
```

## 只生成布局，不连接 Isaac Sim

`--layout-only` 只生成 JSON，不连接 gRPC 服务：

```bash
docker exec -it data_collection_open_source bash -lc '
  export SIM_ASSETS=/geniesim_assets
  cd /geniesim/main/data_collection
  /isaac-sim/python.sh scripts/preview_layout.py --layout-only \
    --task-template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json \
    --output-dir /geniesim/main/data_collection/layout_only_output \
    --num-episodes 2
'
```

## 常用参数

| 参数 | 作用 |
|---|---|
| `--gui` | 在 Isaac Sim GUI 中加载布局，并在布局之间等待 Enter。 |
| `--layout-only` | 只生成布局，不连接 Isaac Sim。 |
| `--num-episodes N` | 生成 N 个随机布局。 |
| `--skip-generate` | 复用输出目录中已有的布局。 |
| `--instance-ids 0,2` | 只预览指定编号的布局。 |
| `--connect-timeout 5` | 设置 gRPC 就绪检查的共享超时预算。 |
| `--headless` | 无交互加载，并保存相机图像。 |
| `--save-images` | GUI 预览时也保存相机图像。 |
| `--cameras head,left_hand,right_hand` | 指定需要保存的相机。 |

## 常见问题

### 容器不存在

如果终端 2 报错 `No such container`，说明终端 1 尚未创建容器，或容器已经
退出。重新执行终端 1 的容器创建命令。

### 无法连接 localhost:50051

确认终端 1 中的 `data_collector_server.py` 仍在运行，并等待 Isaac Sim 完成
启动。预览脚本不会自动启动服务。

### 输出目录已存在

脚本不会覆盖已有布局。需要重新随机生成时换一个 `--output-dir`；需要复用
现有布局时添加 `--skip-generate`。

### 找不到资产

确认宿主机资产目录是 `/home/user/djy/geniesim_assets`，创建容器前已设置：

```bash
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets
```

容器内应能看到 `/geniesim_assets`，且两个运行命令都设置了
`SIM_ASSETS=/geniesim_assets`。
