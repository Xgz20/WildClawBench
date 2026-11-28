# 版本化 CLI 评分镜像

`versions.json` 管理默认版本、独立标签、构建目录和固定 CLI 版本，沿用执行镜像的版本规范。

| 版本 | 最终镜像 | CLI |
| --- | --- | --- |
| v0.1 | `wildclawbench-e2e-scorer:codex-0.171.0-office-v2` | Codex 0.171.0、DSH 0.1.2-rc.1 |
| v0.2（独立构建） | `wildclawbench-e2e-scorer:v0.2-amd64` / `v0.2-arm64` | Codex 0.171.0、DSH 0.1.2-rc.1、ClaudeCode 2.1.330 |
| v0.3（增量基线） | `wildclawbench-e2e-scorer:v0.3-amd64` | 同三种 CLI，从旧评分镜像和 ClaudeCode v0.4 镜像增量构建 |
| v0.4（AMD64 默认） | `wildclawbench-e2e-scorer:v0.4-amd64` | Codex 0.172.0、DSH 0.2.2-rc.5、ClaudeCode 2.1.330 |

`v1/` 保留旧构建定义；`v2/` 为三 CLI 独立配方；`v3/` 为 AMD64 增量配方，`v4/` 升级 Codex/DSH。根目录原 Dockerfile、Office/浏览器修复层和旧验收脚本保留兼容。新版本不占用旧镜像标签，历史作业保留冻结镜像 ID。

## 构建与回滚

```bash
bash docker/e2e-scorer/build.sh --version v0.4 --platform linux/amd64
# 没有旧镜像时，使用独立配方：
bash docker/e2e-scorer/build.sh --version v0.2 --platform linux/amd64 --docker-context colima
# Mac ARM64 原生构建：
bash docker/e2e-scorer/build.sh --version v0.2 --platform linux/arm64 --docker-context colima
bash docker/e2e-scorer/build.sh --version v0.1 --docker-context colima
```

默认含 Office；v0.2 的中间标签追加 `-runtime`，v0.3 直接继承已验收的 Office 层。CLI 版本和底座由清单固定，升级时新增目录及版本记录。`--tag` 可创建同配方独立发行标签，不能占用其他目录版本的标签。默认 AMD64 使用 v0.4，显式选择 ARM64 时默认使用 v0.2。v0.2 默认目标为 `linux/amd64`，适用于 Linux AMD64 服务器；Mac ARM64 原生构建需显式选择 `--platform linux/arm64`。Docker 构建和最终运行均传入目标平台，验收同时校验镜像元数据与容器内架构。跨架构构建需要 builder 支持相应模拟器，也可把上下文传至对应架构主机原生构建。

```bash
bash docker/e2e-scorer/build.sh --version v0.2 --platform linux/amd64 --prepare-only --context /tmp/scorer-v02-amd64
# 将整个目录传至目标服务器，无需仓库或主机 Python：
bash /absolute/scorer-v02-amd64/build-prepared.sh
```

默认上下文为 `.cache/headless-scorer-build/<版本>/<架构>`（v0.1 保留旧路径）。Docker Hub 下载受限时，可用 `--base-registry mirror.example` 指定镜像源；仅替换公共 Python/Node 底座的 registry，保留清单中的仓库名和版本，实际引用写入构建清单。可配置 `--npm-registry`、`--pip-index-url`、`--debian-mirror`、`--debian-security-mirror`。代理仅通过 `--http-proxy` 或运行时 `HTTP_PROXY_INNER` / `HTTPS_PROXY_INNER` 注入，不写入上下文。

## 验收与回执

独立配方使用冻结 Score Skill 创建 Python 3.11 受管环境，并以同一解释器安装 Chromium；增量配方要求旧运行时锁与新 Skill 完全一致，重新执行其运行时探针。公开合成探针验证浏览器点击、键盘、窄窗口、减少动画、网络阻断和截图，以及 DOCX/XLSX/PPTX 转 PDF、中文字体、公式重算为 42 和输入未改写。最终在无网络、无凭据、无主机挂载容器内复验全部 CLI 实际版本及浏览器/Office；不调用模型或消费正式题目。

- `build-manifest.json`：目录版本、CLI/底座参数、构建文件 SHA、Skill 来源与 SHA。
- `runtime-validation.json`：实测 CLI 版本及浏览器/Office 验收。
- `image-receipt.txt`：镜像 ID、架构与能力标签。

Chromium 真实目录为 `/opt/scoring-runtime/playwright-browsers`。旧符号链接别名由 Worker 解析后再交给冻结 Skill 校验。运行时失败为评测异常，不计能力零分。

## 平台接入

在「镜像与模板 → CLI 评分镜像」登记新标签、核验并发布。三个 `org.astron.eval.*.version` 标签声明各 CLI 能力，可同时或分别设置默认版本；任务也可指定已发布版本。旧两 CLI 镜像仍供 Codex/DSH 选择，不能供 ClaudeCode 使用。需同步部署包含 ClaudeCode 支持的框架评分入口与平台版本。

ClaudeCode 仅匹配具有 **Anthropic** 端点和裁判用途的模型，推理档位为 `low/medium/high/xhigh/max`，默认 `high`。运行时凭据 `E2E_SCORER_API_KEY` 被转为 `ANTHROPIC_API_KEY`，端点转为 `ANTHROPIC_BASE_URL`，不进入构建上下文。模型身份从原生 init 事件读回；推理档位依据显式 `--effort` 参数，回执区分二者。启动使用隔离配置目录、空设置来源和严格空 MCP 配置，并保留输入完整性检查。

首次环境导入也可使用：

```dotenv
WCB_E2E_SCORING_IMAGES={"codex":"wildclawbench-e2e-scorer:v0.4-amd64","deepseek-harness":"wildclawbench-e2e-scorer:v0.4-amd64","claudecode":"wildclawbench-e2e-scorer:v0.4-amd64"}
WCB_E2E_SCORING_DOCKER_CONTEXT=default
```

已有 GUI 默认配置不由环境变量覆盖。构建、登记和服务部署分开；回滚时为后续作业选择旧版本，保留既有作业的冻结配置。

模型 ID 原样传入 CLI，不自动增加供应商前缀。例如此网关使用 `claude-opus-5`，不能替换成 `anthropic/claude-opus-5`。

先前本机产物 `wildclawbench-e2e-scorer:v0.2` 为 ARM64，继续保留；新构建使用带架构后缀的标签，禁止覆盖旧通用标签或另一架构的官方标签。

## v0.3 增量构建前提

Docker daemon 上须已存在 `wildclawbench-e2e-scorer:codex-0.171.0-office-v1` 和 `wildclawbench-claudecode-ubuntu:v0.4`，且均为 AMD64。构建只复制后者的 npm CLI 安装目录，不复制登录目录或账户配置；原镜像保持只读。旧评分运行时的锁摘要必须与冻结 Skill 完全一致，随后重新执行 Skill 运行时探针、三种 CLI、浏览器和 Office 验收。源镜像 ID 记录在 `source-images.txt`。没有这些预置镜像时使用 v0.2 独立配方。

## v0.4 CLI 升级

v0.4 固定 npm `latest` 通道在 2026-11-28 对应的 Codex 0.172.0 和 DSH 0.2.2-rc.5，保留 ClaudeCode 2.1.330。继承已验收的 v0.3-amd64，只更新两种 CLI。准备上下文时需要 npm，下载 Linux AMD64 的包缓存且不在准备机执行生命周期脚本；服务器使用缓存执行安装。可用 `--npm-cache-dir` 复用带有 `cache-info.json` 的已准备缓存。缓存仅作为 BuildKit 临时挂载，不进入镜像层，源码清单记录其平台、CLI 版本和内容 SHA256。既有 v0.1/v0.2/v0.3 不变。

CLI 在线验证的端点须与协议匹配：Codex 使用 OpenAI Responses，DSH 使用 OpenAI Chat/Responses，ClaudeCode 使用 Anthropic Messages。OpenAI 端点通常包含 `/v1`；Anthropic SDK 会追加 `/v1/messages`，二者的 base URL 不应直接混用。
