# AstronCode 0.0.13 Harness 镜像集成设计

## 决策摘要

本次集成新增 AstronCode 0.0.13 的 v3 评测镜像，并将 AstronCode runner 从 `astron-spark`/OpenRouter 两路配置扩展为 `astron-spark`、`one-iflytek`、OpenRouter 三路配置。provider 默认按模型名自动识别，允许通过环境变量显式覆盖；新增凭证变量均为可选项，现有评测命令中的 `ASTRON_API_KEY`、`ASTRON_SPARK_API_KEY`、`OPENROUTER_API_KEY` 继续有效。

评测结果目录中的 `config.toml` 始终是脱敏副本。完整单测集作为代码验收门禁；端到端验证只运行 macOS 本地调试指南中 `xsparkx2agent`、`xopglm52`、`gpt-5.5` 三个 AstronCode 单题冒烟用例。

## 现状与依据

- `docker/astroncode/v2/Dockerfile` 面向 AstronCode 0.0.6+，默认安装 npm registry 的最新版本，不能稳定复现 0.0.13。
- `src/agents/astroncode/runner.py` 当前仅将 `xspark*`、`xop*` 识别为 `astron-spark`，其他模型进入 OpenRouter。该规则无法覆盖 0.0.13 模型目录中的 `xminimaxm25`、`astronclaw-auto`，也不会为 `gpt-*` 生成 `one-iflytek` 配置。
- `docker/astroncode/v3/AstronCode-0.0.13版本集成.md` 给出了 0.0.13 的两类最小配置：Astron 模型使用 `astron-spark`，GPT 模型使用 `one-iflytek`。`one-iflytek` 要求 Responses API、关闭 OpenAI 登录校验，并设置 300 秒流空闲超时。
- 当前 runner 已分别生成容器内实际配置和宿主机脱敏配置。评测结果示例中的 OpenRouter 配置只记录 `env_key = "OPENROUTER_API_KEY"`，不包含 Key 值。

## 目标与非目标

### 目标

1. 可重复构建包含 AstronCode 0.0.13 的 Harness 镜像。
2. MaaS/Astron、GPT/one-iflytek 和其他 OpenRouter 模型均获得正确的运行时配置。
3. 现有 `openrouter/<modelId>` 参数和现有凭证变量继续可用。
4. 评测产物、日志和异常信息不泄露模型服务凭证。
5. 更新构建、部署和本地调试文档，使默认镜像和示例与 v3 一致。

### 非目标

- 不修改 v1、v2 镜像内容，也不删除旧版本构建入口。
- 不把 0.0.13 的完整模型目录复制或烘焙进镜像；模型目录继续由 AstronCode 自身管理。
- 不修改 AstronClaw、Codex、OpenCode 等其他 Harness 的 provider 行为。
- 不运行全量 60 题端到端评测。

## 方案设计

### v3 镜像与构建入口

新增 `docker/astroncode/v3/Dockerfile`：

- 基础镜像继续使用 `wildclawbench-codex-ubuntu:v0.0`。
- `ASTRON_CODE_VERSION` 默认值固定为 `0.0.13`，仍允许通过构建参数覆盖。
- npm registry 默认值沿用 v2 的 iFlytek 内网地址。
- 安装后执行 `astron-code --version`，构建阶段即可发现包安装或 CLI 入口异常。
- 创建权限为 `700` 的 `/root/.acode`，运行时配置不进入镜像层。

更新 `script/build-astroncode-image.sh`：

- 默认 `ASTRONCODE_DOCKER_VARIANT=v3`。
- 默认 `IMAGE_TAG=v0.3`。
- 保留 v1/v2 variant、版本覆盖、registry 覆盖和代理构建参数。

更新默认运行镜像及部署文档：

- `AstronCodeAgent` 默认镜像改为 `wildclawbench-astroncode-ubuntu:v0.3`。
- `docs/local/deploy/export.astroncode.sh` 默认导出同一标签。
- `docs/local/guide/linux-评测命令速查.md` 和 `docs/local/guide/macos-本地调试指南.md` 的 AstronCode 章节改为 0.0.13/v0.3，并移除已废弃的 `ASTRON_MODELS_BASE_URL` 示例。

### 模型归一化与 provider 选择

框架侧继续接受 `openrouter/<modelId>`。runner 先剥离历史前缀，再按以下优先级选择 provider：

1. `ASTRONCODE_MODEL_PROVIDER` 非空时使用显式值。
2. 模型名以 `gpt-` 开头时使用 `one-iflytek`。
3. 模型名以 `xminimax`、`xop`、`xspark` 或 `astronclaw-` 开头时使用 `astron-spark`。
4. 其他模型使用 `openrouter`。

`ASTRONCODE_MODEL_PROVIDER` 只接受 `astron-spark`、`one-iflytek`、`openrouter`。非法值在写配置前报错，并列出允许值。显式覆盖用于远程 Astron 模型目录新增尚未纳入自动规则的模型，不改变历史命令格式。

### provider 配置与凭证优先级

#### astron-spark

Key 按以下顺序解析：

1. `ASTRON_API_KEY`
2. `ASTRON_SPARK_API_KEY`
3. `OPENROUTER_API_KEY`

配置包含 `[model_providers.astron-spark]`、`name = "Astron Spark"` 和 `experimental_bearer_token`。0.0.13 最小配置不再写 `models_base_url`。

#### one-iflytek

Key 按以下顺序解析：

1. `ONE_IFLYTEK_API_KEY`
2. `OPENROUTER_API_KEY`

Base URL 按以下顺序解析：

1. `ONE_IFLYTEK_BASE_URL`
2. `OPENROUTER_BASE_URL`
3. `https://one.iflytek.com/api/llm/console/chat/v1`

配置包含：

```toml
[model_providers.one-iflytek]
name = "Codex via iFlytek One"
base_url = "https://one.iflytek.com/api/llm/console/chat/v1"
experimental_bearer_token = "<运行时 Key>"
wire_api = "responses"
requires_openai_auth = false
stream_idle_timeout_ms = 300000
```

#### openrouter

未匹配内置 provider 的模型继续使用 `OPENROUTER_BASE_URL` 和 `OPENROUTER_API_KEY`。配置保留 `env_key = "OPENROUTER_API_KEY"`，不把 Key 写入 TOML。

### 思考深度

`spec.thinking` 或 `ASTRONCODE_REASONING_EFFORT` 非空时写入 `model_reasoning_effort`；两者都为空时不写该字段，由 0.0.13 模型目录采用模型默认值。runner 不对未声明的模型强制写 `high`、`max` 或 `ultra`，避免产生模型不支持的思考深度。

### 运行期配置与脱敏产物

runner 为每次评测生成两份配置：

- 容器内 `/root/.acode/config.toml` 使用实际 bearer token，仅供该任务容器运行。
- 评测输出目录中的 `config.toml` 使用同一配置结构，但将所有 `experimental_bearer_token` 值替换为 `***`。OpenRouter 配置只保留环境变量名。

配置错误、日志和执行状态不得包含 Key。正常清理任务容器后，容器内明文配置随容器删除；宿主机只保留脱敏副本。

## 兼容性与失败策略

- 现有 MaaS 命令已提供 `ASTRON_API_KEY`，无需增加变量。
- 现有 GPT 命令只要提供 `OPENROUTER_API_KEY`，即可通过回退规则生成 `one-iflytek` bearer token。
- `ONE_IFLYTEK_API_KEY`、`ONE_IFLYTEK_BASE_URL` 用于同一进程需要同时区分 OpenRouter 与 iFlytek One 凭证或地址的场景，不是必填项。
- 当前 provider 缺少所需 Key 时立即失败，错误信息列出该 provider 接受的变量，不要求配置无关 provider 的凭证。
- v3 构建或运行异常时，可将 `ASTRONCODE_DOCKER_VARIANT` 和 `DOCKER_IMAGE_ASTRONCODE` 切回 v2/v0.2；v1/v2 文件保持不变。

## 测试与验收

### 自动化测试

新增 AstronCode 配置单元测试，至少覆盖：

- 三类 provider 的自动识别。
- `ASTRONCODE_MODEL_PROVIDER` 的合法覆盖和非法值错误。
- `openrouter/<modelId>` 前缀剥离不影响 provider 判断。
- 三类 Key 及 one-iflytek Base URL 的优先级和兼容回退。
- 使用 `tomllib` 解析三类生成配置，核对 0.0.13 字段、布尔值和整数类型。
- MaaS 与 one-iflytek 宿主机配置中的 bearer token 为 `***`，且测试假 Key 不出现在产物、日志和异常信息中。
- 构建脚本默认 variant/tag 与 runner 默认镜像一致。

运行完整单测集：

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
uv run python -m unittest discover -s tools/report/tests -p 'test_*.py'
```

### 镜像与端到端验收

构建 v3 镜像并确认：

```bash
docker run --rm wildclawbench-astroncode-ubuntu:v0.3 astron-code --version
```

输出应包含 `0.0.13`。

按更新后的 `docs/local/guide/macos-本地调试指南.md` §4.2，使用统一任务 `03_Social_Interaction_task_2_chat_action_extraction`，依次运行：

- `xsparkx2agent`
- `xopglm52`
- `gpt-5.5`

每个模型满足以下条件才通过：

- `score.json` 产生数值分且不含顶层执行错误。
- `execution_status.json` 为 `finished`、`exit_code=0`，并记录 `harness_version=0.0.13`。
- `usage.json` 的模型 token 用量非 0。
- 结果目录中的 `config.toml` provider 正确，且不包含实际 Key。

GPT 冒烟依赖本机可访问 `one.iflytek.com`；无法访问时属于环境阻塞，不能以 MaaS 冒烟通过替代 one-iflytek 验收。

## 风险与边界

- Astron 远程模型目录可独立更新。自动规则未覆盖的新命名需临时使用 `ASTRONCODE_MODEL_PROVIDER=astron-spark`，并在确认命名规律后更新规则和测试。
- 端到端冒烟会调用真实模型和裁判服务，结果受网络、限流和服务状态影响；失败时应结合 `execution_status.json`、`agent.log` 和脱敏 `config.toml` 区分代码问题与外部服务问题。
- 文档当前包含可直接运行的 Key。实现不新增或复制 Key；若现有值仍有效，应独立完成凭证轮换和文档脱敏，该事项不属于本次 Harness 行为改造。
