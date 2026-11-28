# 版本化 CLI 评分镜像

`versions.json` 管理默认版本、独立标签、构建目录和固定 CLI 版本，沿用执行镜像的版本规范。

| 版本 | 最终镜像 | CLI |
| --- | --- | --- |
| v0.1 | `wildclawbench-e2e-scorer:codex-0.171.0-office-v2` | Codex 0.171.0、DSH 0.1.2-rc.1 |
| v0.2（默认） | `wildclawbench-e2e-scorer:v0.2` | Codex 0.171.0、DSH 0.1.2-rc.1、ClaudeCode 2.1.330 |

`v1/` 保留旧构建定义；`v2/` 为新三 CLI 版本。根目录原 Dockerfile、Office/浏览器修复层和旧验收脚本保留兼容。新版本不占用旧镜像标签，历史作业保留冻结镜像 ID。

## 构建与回滚

```bash
bash docker/e2e-scorer/build.sh --docker-context colima
bash docker/e2e-scorer/build.sh --version v0.1 --docker-context colima
```

默认含 Office；中间标签追加 `-runtime`。CLI 版本和底座由清单固定，升级时新增目录及版本记录。`--tag` 可创建同配方独立发行标签，不能占用其他目录版本的标签。Mac 构建为 ARM64；AMD64 服务器应在目标机器构建。

```bash
bash docker/e2e-scorer/build.sh --version v0.2 --prepare-only --context /tmp/scorer-v02
# 将整个目录传至目标服务器，无需仓库或主机 Python：
bash /absolute/scorer-v02/build-prepared.sh
```

默认上下文为 `.cache/headless-scorer-build/<版本>`。可配置 `--npm-registry`、`--pip-index-url`、`--debian-mirror`、`--debian-security-mirror`。代理仅通过 `--http-proxy` 或运行时 `HTTP_PROXY_INNER` / `HTTPS_PROXY_INNER` 注入，不写入上下文。

## 验收与回执

冻结 Score Skill 创建 Python 3.11 受管环境，使用同一解释器安装 Chromium。公开合成探针验证浏览器点击、键盘、窄窗口、减少动画、网络阻断和截图，以及 DOCX/XLSX/PPTX 转 PDF、中文字体、公式重算为 42 和输入未改写。最终在无网络、无凭据、无主机挂载容器内复验全部 CLI 实际版本及浏览器/Office；不调用模型或消费正式题目。

- `build-manifest.json`：目录版本、CLI/底座参数、构建文件 SHA、Skill 来源与 SHA。
- `runtime-validation.json`：实测 CLI 版本及浏览器/Office 验收。
- `image-receipt.txt`：镜像 ID、架构与能力标签。

Chromium 真实目录为 `/opt/scoring-runtime/playwright-browsers`。旧符号链接别名由 Worker 解析后再交给冻结 Skill 校验。运行时失败为评测异常，不计能力零分。

## 平台接入

在「镜像与模板 → CLI 评分镜像」登记新标签、核验并发布。三个 `org.astron.eval.*.version` 标签声明各 CLI 能力，可同时或分别设置默认版本；任务也可指定已发布版本。旧两 CLI 镜像仍供 Codex/DSH 选择，不能供 ClaudeCode 使用。需同步部署包含 ClaudeCode 支持的框架评分入口与平台版本。

ClaudeCode 仅匹配具有 **Anthropic** 端点和裁判用途的模型，推理档位为 `low/medium/high/xhigh/max`，默认 `high`。运行时凭据 `E2E_SCORER_API_KEY` 被转为 `ANTHROPIC_API_KEY`，端点转为 `ANTHROPIC_BASE_URL`，不进入构建上下文。模型身份从原生 init 事件读回；推理档位依据显式 `--effort` 参数，回执区分二者。启动使用隔离配置目录、空设置来源和严格空 MCP 配置，并保留输入完整性检查。

首次环境导入也可使用：

```dotenv
WCB_E2E_SCORING_IMAGES={"codex":"wildclawbench-e2e-scorer:v0.2","deepseek-harness":"wildclawbench-e2e-scorer:v0.2","claudecode":"wildclawbench-e2e-scorer:v0.2"}
WCB_E2E_SCORING_DOCKER_CONTEXT=default
```

已有 GUI 默认配置不由环境变量覆盖。构建、登记和服务部署分开；回滚时为后续作业选择旧版本，保留既有作业的冻结配置。
