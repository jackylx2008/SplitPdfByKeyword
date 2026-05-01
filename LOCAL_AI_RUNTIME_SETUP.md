# Local AI Runtime Setup

本文档记录当前项目的本地 AI 运行环境：CUDA 基础检查、Python 虚拟环境、`llama.cpp` 服务启动，以及通过根目录脚本验证本地模型调用。

## 当前项目约定

- Python 环境：项目根目录下的 `.venv`
- 配置入口：`config.yaml`
- 本机私有配置：`common.env`
- 本地模型服务：`llama-server.exe`
- API 形式：OpenAI 兼容 HTTP API
- 默认 API 地址：`http://127.0.0.1:8080/v1`
- 自检入口脚本：`ai_self_check.py`

代码结构遵循 `COMMON_PROJECT_SKILLS.md`：

- `src/localai/modules/`：基础能力模块
- `src/localai/flows/`：场景编排层
- 项目根目录 `.py` 文件：独立入口脚本

## 1. CUDA 基础检查

在项目根目录执行：

```powershell
nvidia-smi
```

正常情况下应看到：

- NVIDIA 显卡名称
- Driver Version
- CUDA Version
- 显存占用信息

这个检查确认驱动与 CUDA 运行能力可被系统识别。当前项目调用 `llama.cpp` 的 CUDA 能力，主要依赖已编译好的 `llama-server.exe` 及其同目录 CUDA 后端 DLL。

## 2. Python 环境

创建虚拟环境：

```powershell
python -m venv .venv
```

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

当前 Python 依赖保持很轻，只需要项目配置读取等基础能力；本地模型推理通过 `llama-server` 的 HTTP API 完成，不在 Python 进程内加载 GGUF。

## 3. 本机配置

真实机器路径写在 `common.env`，该文件不入库；仓库只保留 `common.env.example`。

关键变量：

```dotenv
LLAMACPP_BASE_URL=http://127.0.0.1:8080/v1
LLAMACPP_MODEL=local-model
LLAMACPP_AUTOSTART=true

LLAMACPP_SERVER_PATH=
LLAMACPP_MODEL_PATH=
LLAMACPP_MMPROJ_PATH=
LLAMACPP_N_GPU_LAYERS=999

LLAMACPP_REASONING=off
LLAMACPP_REASONING_BUDGET=0
```

说明：

- `LLAMACPP_SERVER_PATH` 指向已编译好的 `llama-server.exe`
- `LLAMACPP_MODEL_PATH` 指向主模型 `.gguf`
- `LLAMACPP_MMPROJ_PATH` 指向多模态投影文件；纯文本场景可留空
- `LLAMACPP_MODEL` 会作为 `llama-server --alias` 传入，Python 请求使用这个稳定模型名
- `LLAMACPP_REASONING=off` 和 `LLAMACPP_REASONING_BUDGET=0` 用于让 Qwen3 类模型在自检时直接返回 `message.content`

## 4. 自动启动流程

运行入口脚本时，项目会执行以下流程：

1. 读取 `common.env`
2. 读取并解析 `config.yaml`
3. 检查 `nvidia-smi`
4. 请求 `GET /health`
5. 请求 `GET /v1/models`
6. 如果服务不可用且 `LLAMACPP_AUTOSTART=true`，自动启动 `llama-server`
7. 轮询等待服务可用
8. 校验配置模型名是否存在于模型列表
9. 可选调用 `POST /v1/chat/completions`

自动启动命令由配置生成，核心参数等价于：

```powershell
& $env:LLAMACPP_SERVER_PATH `
  -m $env:LLAMACPP_MODEL_PATH `
  --mmproj $env:LLAMACPP_MMPROJ_PATH `
  --alias $env:LLAMACPP_MODEL `
  -ngl $env:LLAMACPP_N_GPU_LAYERS `
  --reasoning $env:LLAMACPP_REASONING `
  --reasoning-budget $env:LLAMACPP_REASONING_BUDGET `
  --host 127.0.0.1 `
  --port 8080 `
  --verbose
```

如果 `LLAMACPP_MMPROJ_PATH` 为空，启动命令不会传 `--mmproj`。

## 5. 项目自检

只检查 CUDA、服务健康状态和模型列表，不发送对话请求：

```powershell
.\.venv\Scripts\python.exe ai_self_check.py --no-chat
```

完整端到端检查：

```powershell
.\.venv\Scripts\python.exe ai_self_check.py --max-tokens 64 --prompt "请直接回答两个字：可用"
```

成功时会输出类似：

```json
{
  "cuda_check": {
    "command": "nvidia-smi",
    "ok": true
  },
  "llamacpp": {
    "base_url": "http://127.0.0.1:8080/v1",
    "model": "local-model",
    "health": {
      "status": "ok"
    },
    "available_models": [
      "local-model"
    ]
  },
  "answer": "可用"
}
```

## 6. 手动接口检查

服务启动后，可以直接检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/v1/models
```

手动发送一次 OpenAI 兼容请求：

```powershell
$body = @{
  model = $env:LLAMACPP_MODEL
  temperature = 0
  max_tokens = 64
  messages = @(
    @{
      role = "user"
      content = "请直接回答两个字：可用"
    }
  )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8080/v1/chat/completions" `
  -ContentType "application/json" `
  -Body $body
```

## 7. 日志与排错

项目日志：

```text
log/<entry_name>.log
```

`llama-server` 输出：

```text
log/llama_server.out.log
log/llama_server.err.log
```

常见问题：

- `nvidia-smi` 不可用：先检查 NVIDIA 驱动是否正常安装
- `/health` 不可用：检查端口是否被占用，或 `LLAMACPP_SERVER_PATH` 是否正确
- 模型不存在：检查 `LLAMACPP_MODEL_PATH`，并确认 `.gguf` 文件存在
- 请求模型名不匹配：访问 `/v1/models`，将 `LLAMACPP_MODEL` 改为返回的模型 id，或使用 `--alias` 保持稳定名称
- 只返回 reasoning、不返回 content：确认 `LLAMACPP_REASONING=off` 和 `LLAMACPP_REASONING_BUDGET=0`，然后重启 `llama-server`
- 中文输出乱码：使用项目入口脚本输出；脚本已将 stdout 设置为 UTF-8

停止本地服务：

```powershell
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process
```

## 8. 新入口脚本接入方式

新增一个根目录入口脚本时，应保持入口层很薄：

1. 调用 `bootstrap_context(__file__)`
2. 初始化配置、日志和上下文
3. 调用 `src/localai/flows/` 中对应的 `run(...)`
4. 用 `print_json(...)` 输出结构化结果

需要调用本地模型时，优先在 `flows` 中组合：

- `LlamaCppConfig.from_config(...)`
- `LlamaCppClient.ensure_server()`
- `LlamaCppClient.assert_model_available(...)`
- `LlamaCppClient.chat(...)`

不要在入口脚本里直接拼接模型路径、启动命令或 HTTP 请求。
