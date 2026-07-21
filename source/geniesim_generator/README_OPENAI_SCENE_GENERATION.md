# 使用 OpenAI 自然语言生成 GenieSim 场景

本文重点说明如何运行一个完整 demo：启动资产检索和 Open WebUI、输入自然语言、保存生成代码、编译场景，并检查生成结果。

本文命令适用于当前宿主机：

- 仓库：`/home/user/djy/genie_sim`
- Conda 环境：`geniesim-generator`
- 资产包：`/home/user/djy/geniesim_assets`
- OpenAI Key 文件：`source/geniesim_generator/openai_key.yaml`
- Open WebUI：`http://127.0.0.1:3000`
- MCP 资产服务：`http://127.0.0.1:8765`

## 一、运行 demo

### 1. 进入环境并加载运行变量

打开一个终端：

```bash
cd /home/user/djy/genie_sim
conda activate geniesim-generator

export OPENAI_API_KEY="$(tr -d '\r\n' < \
  /home/user/djy/genie_sim/source/geniesim_generator/openai_key.yaml)"

export GENIESIM_ASSETS_DIR="$(python -c \
  'import geniesim_assets, os; print(os.path.dirname(geniesim_assets.__file__))')"
```

检查变量是否已经设置，但不要打印 Key：

```bash
test -n "$OPENAI_API_KEY" && echo "OPENAI_API_KEY is set"
test -d "$GENIESIM_ASSETS_DIR" && echo "GENIESIM_ASSETS_DIR=$GENIESIM_ASSETS_DIR"
```

`openai_key.yaml` 当前保存的是原始 Key 字符串，不需要使用 `yaml` 命令解析。不要把该文件加入 Git。

### 2. 启动 Open WebUI 和资产检索服务

```bash
cd /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator

BUILDX_CONFIG=/tmp/geniesim-buildx \
docker compose --profile text up -d --build
```

`text` profile 使用 OpenAI `text-embedding-3-small` 建立资产向量索引，不需要 GPU。第一次启动时需要为资产建立索引，MCP 服务可能比 Open WebUI 晚一到数分钟就绪。

### 3. 检查服务

以下命令仍需在刚才加载了环境变量的终端中执行：

```bash
docker compose ps

curl -fsS http://127.0.0.1:3000/health

curl -fsS http://127.0.0.1:8765/assets-agent/openapi.json \
  | python -m json.tool
```

正常情况下：

- `open-webui` 显示为 `Up ... (healthy)`；
- `assets-retrieval-agent_text` 显示为 `Up`；
- WebUI health 返回 `{"status":true}`；
- MCP OpenAPI 结果中的 `paths` 包含 `/search_assets`。

也可以直接测试一次资产检索：

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"transparent beverage bottle","topk":1}' \
  http://127.0.0.1:8765/assets-agent/search_assets \
  | python -m json.tool
```

### 4. 在 Open WebUI 输入自然语言

1. 浏览器打开 `http://127.0.0.1:3000`。
2. 在模型选择器中选择 `GenieSim Generator`。
3. 输入自然语言场景描述，例如：

```text
生成一个简单桌面场景：一张桌子上放一个透明饮料瓶和一个白色碗，
饮料瓶位于左侧，碗位于右侧，两件物体之间留出明显间距；
物体不能互相碰撞，不能悬空，也不能超出桌面。
```

4. 等待模型自动调用 `search_assets` 等资产工具并返回 Python 代码。
5. 在生成结果上执行 `Save Code to File` 动作。

保存动作会把代码写入：

```text
/home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator/LLM_RESULT.py
```

当前保存动作兼容传统 Markdown 代码块，以及 Open WebUI Responses 格式中
位于 `originalContent` 或 `output_text` 的裸 Python 输出。更新动作源码后，运行：

```bash
python source/geniesim_generator/scripts/sync_save_action_export.py
```

然后重新导入并启用生成的 `config/function-save_code_to_file.json`；Open WebUI
会把导入的动作保存在数据库中，不会自动跟随宿主机源码变化。

检查文件是否已更新：

```bash
ls -l /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator/LLM_RESULT.py
sed -n '1,80p' /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator/LLM_RESULT.py
```

生成代码必须包含名为 `root_scene()` 的注册场景入口。

### 5. 编译生成的场景

```bash
cd /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator

export GENIESIM_GENERATOR_OUTPUT_DIR=\
/home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task

PYTHONPATH=/home/user/djy/genie_sim/source/geniesim_generator/src \
python app.py --scene_id natural_language_tabletop_demo
```

`--scene_id natural_language_tabletop_demo` 的含义是：将输出放入名为 `natural_language_tabletop_demo` 的目录。它不是资产 ID，也不需要事先注册。建议只使用小写字母、数字和下划线，例如：

```text
office_desk_demo
kitchen_table_demo
complex_tabletop_01
```

相同 `scene_id` 每运行一次会新增一个数字实例目录，不会覆盖已有实例。第一次运行通常生成 `0`，之后依次生成 `1`、`2` 等。

编译成功时终端会输出：

```text
step3: save scene to .../natural_language_tabletop_demo/0/scene.usda...
Scene Graph DAG is Here!
```

### 6. 检查生成结果

```bash
cd /home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task

find natural_language_tabletop_demo -maxdepth 2 -type f | sort
```

第一次运行的目录结构如下：

```text
natural_language_tabletop_demo/
└── 0/
    ├── LLM_RESULT.py
    ├── graph.dot
    ├── graph.svg
    ├── scene.usda
    └── scene_info.json
```

各文件用途：

- `scene.usda`：生成的 OpenUSD 场景；
- `scene_info.json`：物体 ID、位姿、标签和关系元数据；
- `graph.svg`：场景生成调用关系图，可直接用浏览器打开；
- `graph.dot`：关系图的 Graphviz 源文件；
- `LLM_RESULT.py`：生成该实例时使用的 Python DSL 快照。

检查 USD 是否可以加载：

```bash
cd /home/user/djy/genie_sim

conda run -n geniesim-generator python -c \
  "from pxr import Usd; p='source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task/natural_language_tabletop_demo/0/scene.usda'; s=Usd.Stage.Open(p); assert s; print('USD OK, prims =', sum(1 for _ in s.Traverse()))"
```

如果本次生成的实例不是 `0`，请把命令中的实例编号改成实际编号。

## 二、再次生成其他场景

服务保持运行时，不需要重新执行 Docker 启动命令。直接在 Open WebUI 中输入新的描述、执行 `Save Code to File`，然后换一个 `scene_id` 编译：

```bash
cd /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator

PYTHONPATH=/home/user/djy/genie_sim/source/geniesim_generator/src \
GENIESIM_GENERATOR_OUTPUT_DIR=/home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task \
python app.py --scene_id kitchen_table_demo
```

更复杂的提示词可以明确指定：

- 物体类别、数量、颜色和材质；
- 左右、前后、上下、包含、堆叠等空间关系；
- 桌面边界、物体间距和禁止碰撞；
- 随机物体选择、随机位姿或有限范围内的布局变化。

不要在提示词中猜测资产 ID。让模型先调用资产检索工具，再使用返回的真实 ID。

## 三、服务管理

进入 Compose 目录并重新加载变量：

```bash
cd /home/user/djy/genie_sim
conda activate geniesim-generator

export OPENAI_API_KEY="$(tr -d '\r\n' < \
  /home/user/djy/genie_sim/source/geniesim_generator/openai_key.yaml)"
export GENIESIM_ASSETS_DIR=/home/user/djy/geniesim_assets

cd source/geniesim_generator/src/geniesim_generator
```

查看日志：

```bash
docker compose logs -f --tail=100 open-webui mcp-server_text
```

重新启动：

```bash
docker compose restart open-webui mcp-server_text
```

停止并删除容器，但保留本地配置和索引数据：

```bash
docker compose --profile text down
```

重新启动已有服务且不强制构建镜像：

```bash
docker compose --profile text up -d
```

## 四、常见问题

### MCP 端口 8765 暂时无法访问

第一次启动时正在建立资产索引。查看进度：

```bash
docker compose logs -f --tail=100 mcp-server_text
```

看到资产同步完成后，再访问 `/assets-agent/openapi.json`。

### 访问 8080 不是 Open WebUI

当前 Open WebUI 固定使用 `3000`，因为宿主机的 `8080` 可能已被其他服务占用。请访问：

```text
http://127.0.0.1:3000
```

### Compose 提示缺少变量

如果出现 `set OPENAI_API_KEY` 或 `set GENIESIM_ASSETS_DIR`，说明当前终端没有加载变量。重新执行“运行 demo”的第 1 步。Docker 容器已经运行并不代表新终端自动继承这些变量。

### WebUI 中没有 GenieSim Generator

检查是否已经导入：

```text
source/geniesim_generator/src/geniesim_generator/config/geniesimscenegen.json
```

在 Open WebUI 管理界面导入该模型配置，并确认基础模型为 `gpt-5.6-sol`。该配置已经包含工具调用所需的 `reasoning_effort: none`。

### WebUI 中没有 Save Code to File

检查是否已经导入并启用：

```text
source/geniesim_generator/src/geniesim_generator/config/function-save_code_to_file.json
```

动作需要处于 active 状态；作为 global 动作启用后，可以在生成结果上直接执行。

### 编译时找不到资产或输出目录

确认两个目录存在：

```bash
test -d /home/user/djy/geniesim_assets
test -d /home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task
```

并确认运行前设置了：

```bash
export GENIESIM_ASSETS_DIR=/home/user/djy/geniesim_assets
export GENIESIM_GENERATOR_OUTPUT_DIR=/home/user/djy/genie_sim/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task
```

### 直接运行 LLM_RESULT.py 失败

不要执行 `python LLM_RESULT.py`。必须从 `app.py` 所在目录运行：

```bash
cd /home/user/djy/genie_sim/source/geniesim_generator/src/geniesim_generator
PYTHONPATH=/home/user/djy/genie_sim/source/geniesim_generator/src \
python app.py --scene_id my_demo
```

`app.py` 使用脚本相对导入，并负责初始化场景 DSL 的实际实现。

### 如何查看三维场景

生成 `scene.usda` 和使用 Isaac Sim 可视化是两个独立步骤。场景编译不要求 Isaac Sim；实时三维预览需要安装了 Isaac Sim 和 GenieSim benchmark 依赖的环境。

具备 Isaac Sim 运行环境时，可以使用 generator 的场景查看器：

```bash
cd /home/user/djy/genie_sim/source/geniesim_generator
python src/geniesim_generator/scene_viewer.py --auto-play
```

如果当前 `geniesim-generator` 环境提示缺少 `omni`、`isaacsim` 或 benchmark 模块，应切换到已安装 Isaac Sim 的 GenieSim 环境，而不是在轻量 generator 环境中补装整套仿真依赖。
