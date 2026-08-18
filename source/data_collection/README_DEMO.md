# Data Collection Demo — Docker 双终端快速上手

本文档说明如何在 **Docker 容器** 中，用 **两个终端** 跑通数据采集 demo。  
建议从 **[推荐 First-Run Demo（G2，由易到难）](#推荐-first-run-demo-g2由易到难)** 第 1 个任务开始；默认完整链路验证可用第 8 个 **苹果分拣**（`sort_the_fruit_into_the_box_apple_g2`）。

完整架构与配置说明见 [README.md](README.md)。

---

## 前置条件

| 项目 | 要求 |
|------|------|
| GPU | NVIDIA GPU（推荐 RTX 40 系列；50 系列 cuRobo 可能不兼容） |
| Docker | 已安装，且支持 `--gpus all` |
| 镜像 | `registry.agibot.com/genie-sim/geniesim3-data-collection:latest` |
| 资产库 | 本机存在 `geniesim_assets` 目录 |

### 1. 构建镜像（首次）

```bash
cd /home/user/djy/genie_sim/source/data_collection
geniesim autocollect build
# 或
docker build -f ./dockerfile -t registry.agibot.com/genie-sim/geniesim3-data-collection:latest .
```

### 2. 配置资产路径（宿主机，必须）

`start_gui.sh` 通过环境变量 `GENIESIM_ASSETS_SRC` 挂载资产库。**每次新开终端跑 demo 前都要设置**（或写入 `~/.bashrc`）：

```bash
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets
```

建议同时 editable 安装（便于 Python 与 CLI 发现资产）：

```bash
pip install -e /home/user/djy/geniesim_assets
```

验证：

```bash
python3 -c "import geniesim_assets; print(geniesim_assets.ASSETS_PATH)"
# 期望输出: /home/user/djy/geniesim_assets
```

---

## 架构说明

数据采集由 **两个进程** 协作完成，必须在 **同一容器** 内运行：

```
┌─────────────────────────────────────────────────────────────┐
│  Docker 容器: data_collection_open_source                   │
│                                                             │
│  Terminal 1                         Terminal 2              │
│  data_collector_server.py    ←gRPC→  run_data_collection.py │
│  (Isaac Sim + 物理 + 相机)            (布局 + 规划 + 录制)    │
└─────────────────────────────────────────────────────────────┘
```

| 终端 | 脚本 | 作用 |
|------|------|------|
| Terminal 1 | `data_collector_server.py` | 启动 Isaac Sim、gRPC 服务（默认 `localhost:50051`） |
| Terminal 2 | `run_data_collection.py` | 生成任务布局、执行采集、写入录制数据 |

> **重要：** 容器内请使用 **`/isaac-sim/python.sh`**（或别名 `omni_python`），**不要**使用系统 `python3`。依赖（含 `grpcio`）安装在 Isaac Sim 的 Python 环境中。

---

## 步骤一：创建并进入容器（仅第一次）

在 **宿主机 Terminal 1** 执行：

```bash
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets
cd /home/user/djy/genie_sim/source/data_collection
./scripts/start_gui.sh run data_collection_open_source
```

成功时会看到：

```
using SIM_REPO_ROOT='.../data_collection'
using geniesim_assets='/home/user/djy/geniesim_assets' -> /geniesim_assets
```

此时 shell 提示符类似 `isaac-sim@user:/geniesim/main/data_collection$`，表示 **已在容器内**。

### `run` / `exec` / `start` 区别

| 命令 | 何时使用 |
|------|----------|
| `./scripts/start_gui.sh run <name>` | **仅第一次**：创建新容器并进入 |
| `./scripts/start_gui.sh exec <name>` | **第 2、3… 个终端**：进入已在运行的同一容器 |
| `./scripts/start_gui.sh start <name>` | 容器已停止但未删除时，重新启动 |

**不要**在两个终端各跑一遍 `run`，否则会因容器名冲突报错。

---

## 步骤二：Terminal 1 — 启动 Isaac 服务端

在 **已进入容器的 Terminal 1** 中执行（会占用该终端，属正常现象）：

```bash
cd /geniesim/main/data_collection

/isaac-sim/python.sh scripts/data_collector_server.py \
  --enable_physics \
  --enable_curobo \
  --publish_ros
```

说明：

- `--enable_physics`：开启物理仿真
- `--enable_curobo`：开启 cuRobo 运动规划
- `--publish_ros`：发布 ROS 消息；**录制数据时必须加**

等待 Isaac Sim 加载完成（GUI 模式会看到窗口；日志不再刷初始化信息即可）。

---

## 步骤三：Terminal 2 — 进入同一容器并启动采集

在 **宿主机** 新开 **Terminal 2**（不要关闭 Terminal 1）：

```bash
cd /home/user/djy/genie_sim/source/data_collection
./scripts/start_gui.sh exec data_collection_open_source
```

进入容器后执行：

```bash
cd /geniesim/main/data_collection

/isaac-sim/python.sh scripts/run_data_collection.py \
  --task_template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json \
  --use_recording
```

说明：

- `--use_recording`：**必须**，否则不会写入 `recording_data/`
- `--task_template`：demo 任务模板路径

---

## 输出位置

| 类型 | 路径（相对 `data_collection/`） |
|------|-----------------------------------|
| 录制数据 | `recording_data/[sort_the_fruit_into_the_box_apple_g2_<N>]/` |
| 预览视频 | `recording_data/.../observations/videos/head_color.mp4` |
| 生成的布局 JSON | `saved_task/sort_the_fruit_into_the_box_apple_g2/` |
| 日志 | `logs/sort_the_fruit_into_the_box_apple_g2/`（若通过 autocollect 一键跑） |

查看某条 episode 是否成功：

```bash
cat recording_data/\[sort_the_fruit_into_the_box_apple_g2_0\]/task_result.json
# "task_status": true 表示任务成功
```

---

## 命令速查（复制粘贴）

### 宿主机 — 首次启动容器

```bash
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets
cd /home/user/djy/genie_sim/source/data_collection
./scripts/start_gui.sh run data_collection_open_source
```

### 容器 Terminal 1 — Server

```bash
/isaac-sim/python.sh scripts/data_collector_server.py --enable_physics --enable_curobo --publish_ros
```

### 宿主机 Terminal 2 — 进入同一容器

```bash
cd /home/user/djy/genie_sim/source/data_collection
./scripts/start_gui.sh exec data_collection_open_source
```

### 容器 Terminal 2 — Client

```bash
/isaac-sim/python.sh scripts/run_data_collection.py \
  --task_template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json \
  --use_recording
```

---

## 常见问题

### 1. `geniesim_assets is not pip-installed`

```bash
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets
```

`start_gui.sh` 只认该环境变量，不会自动搜索 pip 安装路径。

### 2. `ModuleNotFoundError: No module named 'grpc'`

使用了系统 `python3`。请改用：

```bash
/isaac-sim/python.sh scripts/run_data_collection.py ...
```

验证：

```bash
/isaac-sim/python.sh -c "import grpc; print('ok')"
```

### 3. `Failed to connect to gRPC server`

- Terminal 1 的 server 尚未启动或未加载完
- 两个进程不在同一容器
- server 进程已崩溃（查看 Terminal 1 报错）

**顺序：** 先起 server，等就绪后再起 client。

### 4. Terminal 1 退出后 Terminal 2 无法 `exec`

`start_gui.sh run` 使用 `--rm`：在 Terminal 1 输入 `exit` 退出容器 shell 时，容器会被删除。

处理方式：重新 `run` 创建容器，或保持 Terminal 1 中 server 进程运行不要 `exit`。

### 5. 容器名已存在

```bash
docker rm -f data_collection_open_source
export GENIESIM_ASSETS_SRC=/home/user/djy/geniesim_assets
./scripts/start_gui.sh run data_collection_open_source
```

---

## 推荐 First-Run Demo（G2，由易到难）

以下 10 个任务按 **操作步骤数 → 场景干扰 → 语义/推理难度** 排序，适合在跑通环境后依次尝试。  
`tasks/` 前缀均相对于容器内 `/geniesim/main/data_collection/`。

| # | 难度 | 任务 | 模板路径 | 阶段 | 说明 |
|---|------|------|----------|------|------|
| 1 | ★☆☆☆☆ | 拿蓝色笔 | `tasks/geniesim_2025/pick_pen_of_specific_color/g2/pick_pen_of_specific_color_blue.json` | pick | 仅 1 步抓取；2–4 支彩色笔，按颜色筛选，最容易验证 pipeline |
| 2 | ★☆☆☆☆ | 拿红色台球 | `tasks/geniesim_2025/pick_billards_of_specific_color/g2/pick_billards_of_specific_color_red.json` | pick | 球形物体 + 颜色属性， grasp 与 #1 类似 |
| 3 | ★★☆☆☆ | 拿红色积木 | `tasks/geniesim_2025/pick_building_block_of_specific_color/g2/pick_building_block_of_specific_color_red.json` | pick | 方块抓取；仍是一步 pick，物体形状与台球不同 |
| 4 | ★★☆☆☆ | 拿文具 | `tasks/geniesim_2025/pick_up_the_stationery/g2/pick_up_the_stationery.json` | pick | 按类别（文具）选取，桌面若干干扰物 |
| 5 | ★★☆☆☆ | 拿最小苹果 | `tasks/geniesim_2025/pick_fruit_of_specific_size/g2/pick_fruit_of_specific_size_apple_small_g2.json` | pick | 2–5 个不同大小水果，需 **尺寸推理** |
| 6 | ★★★☆☆ | 积木入盒（半圆孔） | `tasks/geniesim_2025/place_blocks_into_box/g2/place_blocks_into_box_001.json` | pick → insert → reset | 三步；形状匹配 + 插入，比纯 pick 难 |
| 7 | ★★★☆☆ | 笔入笔筒 | `tasks/geniesim_2025/put_the_pen_into_the_pen_holder/g2/put_the_pen_into_the_pen_holder_g2.json` | pick → insert → reset | 三步；细长物体精确插入笔筒 |
| 8 | ★★★★☆ | 苹果分拣入盒 | `tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_apple_g2.json` | pick → place → reset | **默认 demo**；多水果干扰 + 两个收纳盒，需 pick 再 place |
| 9 | ★★★★☆ | 物体入红盒 | `tasks/geniesim_2025/place_object_into_box_of_specific_color/g2/place_object_into_box_of_specific_color_red_g2.json` | pick → place → reset | 三步；按盒子颜色放置，3–5 个桌面物体 |
| 10 | ★★★★★ | 拿非红色物品 | `tasks/geniesim_2025/pick_up_with_not_command/g2/pick_up_with_not_command_red.json` | pick | 一步抓取但指令含 **否定语义**（非红），3–7 个干扰物，认知最难 |

### 运行方式

Server 保持运行，只换 client 的 `--task_template`（或任务名）：

```bash
/isaac-sim/python.sh scripts/run_data_collection.py \
  --task_template tasks/geniesim_2025/pick_pen_of_specific_color/g2/pick_pen_of_specific_color_blue.json \
  --use_recording
```

用 CLI 按名称启动（支持唯一子串匹配）：

```bash
geniesim autocollect run pick_pen_of_specific_color_blue --headless --standalone
geniesim autocollect run sort_the_fruit_into_the_box_apple_g2 --headless --standalone
```

### 难度说明

- **★–★★**：仅 `pick` 一阶段；先确认 gRPC、cuRobo、录制链路正常。
- **★★★**：引入 `insert` 或 `place` + `reset`，考察双臂协调与放置精度。
- **★★★★**：多物体干扰 + 分拣/按容器属性放置（#8–#9 为官方 README 常用 demo）。
- **★★★★★**：语言否定/复合指令（#10）；同族还有 `pick_up_with_or_command`（31 个）、`pick_up_with_common_sense`（101 个），建议在上述 10 个跑稳后再试。

### 浏览全部 294 个模板

```bash
geniesim autocollect list --robot=g2
geniesim autocollect list --robot=g2 sort_fruit
geniesim autocollect tasks
```

---

## 自动化：10 个任务各采集 2 条成功轨迹

脚本 [`scripts/run_first_run_demos.py`](scripts/run_first_run_demos.py) 会按上表顺序依次跑 10 个 G2 demo，**每个任务直到凑满 2 条 `task_status: true` 的成功录制**（或达到最大尝试次数）。

### 前置：Server 必须先启动

**Terminal 1（容器内，保持运行）：**

```bash
/isaac-sim/python.sh scripts/data_collector_server.py --enable_physics --enable_curobo --publish_ros
```

### 一键跑全套（Terminal 2，容器内）

```bash
cd /geniesim/main/data_collection

/isaac-sim/python.sh scripts/run_first_run_demos.py \
  --use-recording \
  --target-successes 2 \
  --max-attempts-per-task 30
```

### 常用参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--target-successes` | `2` | 每个任务需要的成功轨迹数 |
| `--max-attempts-per-task` | `30` | 单任务最多尝试次数 |
| `--tasks` | 全部 1–10 | 只跑部分任务，如 `1,3,8` 或 `1-5` |
| `--keep-failed` | 关 | 默认**删除**失败录制以节省磁盘 |
| `--manifest` | `logs/first_run_demos/manifest.json` | 汇总报告 |
| `--dry-run` | — | 只打印计划，不连接 Isaac |

示例：只跑前 3 个简单 pick 任务：

```bash
/isaac-sim/python.sh scripts/run_first_run_demos.py \
  --use-recording --tasks 1-3
```

### 输出

| 类型 | 路径 |
|------|------|
| 成功轨迹 | `recording_data/[<task_id>_0]/`、`...1/` 等 |
| 汇总 manifest | `logs/first_run_demos/manifest.json` |
| 临时布局 JSON | `saved_task/first_run_demos/<task_id>/` |

查看 manifest：

```bash
cat logs/first_run_demos/manifest.json
```

脚本结束时会打印每个任务的成功数；若某任务未凑满 2 条成功，退出码为 `1`。

---

## 换其他 demo 任务

完整任务库见上文 **推荐 First-Run Demo** 与 `geniesim autocollect list`。将 `--task_template` 换成任意 G2 JSON 即可，例如：

```bash
/isaac-sim/python.sh scripts/run_data_collection.py \
  --task_template tasks/geniesim_2025/sort_fruit/g2/sort_the_fruit_into_the_box_orange_g2.json \
  --use_recording
```

---

## 相关文档

- [README.md](README.md) — 完整安装、一键采集、本地部署
- [README_LAYOUT_PREVIEW.md](README_LAYOUT_PREVIEW.md) — 仅生成布局 + Isaac 预览（不采轨迹）
- [README_SAVED_TASK_TO_BENCHMARK.md](README_SAVED_TASK_TO_BENCHMARK.md) — 从 saved task 生成到 benchmark 场景加载
- [TASK_CONFIG_GUIDE.md](TASK_CONFIG_GUIDE.md) — 任务 JSON 配置说明
