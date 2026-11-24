# Claude Code 镜像更新日志

本文记录 WildClawBench Claude Code Harness 的镜像版本、构建来源、运行方式和验证边界。正式构建映射维护在 `docker/claudecode/versions.json`。

## 当前正式镜像

| 记录日期 | 完整镜像 tag | Claude Code | Node.js | 构建来源 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | `wildclawbench-claudecode-ubuntu:v0.4` | `2.1.330` | Node 24 | `docker/claudecode/v4/Dockerfile` |
| 2026-08-28 | `wildclawbench-claudecode-ubuntu:v0.3` | `2.1.250` | Node 24 | 历史版本 |

### v0.4

- 使用官方全局包 `@anthropic-ai/claude-code@2.1.330`，命令为 `claude`。
- 从干净的 `wildclawbench-codex-ubuntu:v0.0` 评测底座重建，不继承旧 `v0.2-patched` 镜像层。
- 使用 `node:24-bookworm-slim` 提供 Node 24，满足 Claude Code 的 Node.js 版本要求。
- 保留底座中的 Google Chrome、Agent Browser、Playwright、Python、Git、jq 和文档处理工具。
- API key、base URL 和模型名只在任务容器启动时注入，镜像不包含运行时凭据或 `.env`。
- 无头执行使用 `--print --output-format stream-json`，原始 transcript 仍落在 `/claude_code/log/chat.json`，保持现有评分和产物收集路径兼容。
- Runner 会优先调用全局 `claude`，显式覆盖为历史镜像时仍可回退到 `/claude_code/start.sh`。

### 验证边界

- 已核对 npm 固定版本、Node 24 runtime、无凭据镜像约束及 `v4` 构建上下文。
- 目标 Docker daemon 构建后应检查 `claude --version` 为 `2.1.330`、Node 为 `v24.x`，并确认 Chrome、Agent Browser、Python、Git、jq 可用。
- 还需补做一条 MaaS 工具调用冒烟，确认全局 `claude` 启动、stream-json transcript、轨迹转换和 usage 产物均正常；静态检查不等价于真实 provider 或全量评测通过。

构建命令：

```bash
bash docker/claudecode/build.sh --version v0.4 --skip-save
```

导出离线镜像时省略 `--skip-save`：

```bash
bash docker/claudecode/build.sh --version v0.4
```

## 历史镜像

| 记录日期 | 完整镜像 tag | Claude Code | 离线包 | 状态 |
| --- | --- | --- | --- | --- |
| 2026-08-16 | `wildclawbench-claudecode-ubuntu:v0.2-patched` | `2.1.88` | `wildclawbench-claudecode-ubuntu_v0.2-patched.tar` | 仅保留兼容，不再作为默认镜像 |

### v0.2-patched 边界

- 镜像使用 `/claude_code/start.sh` 启动非官方源码封装，不是全局 Claude Code CLI。
- 仓库没有该镜像的 Dockerfile，不能从当前代码重建。
- 历史镜像记录在 `versions.json` 的 `legacy_versions` 中；统一构建脚本只接受可重建的正式版本。

## 使用约定

```bash
export DOCKER_IMAGE_CLAUDECODE=wildclawbench-claudecode-ubuntu:v0.4
```

离线加载：

```bash
docker load -i Images/wildclawbench-claudecode-ubuntu_v0.4.tar.gz
```

## 相关实现

- `docker/claudecode/v4/Dockerfile`
- `docker/claudecode/v3/Dockerfile`（历史版本）
- `docker/claudecode/versions.json`
- `docker/claudecode/build.sh`
- `src/agents/claudecode/runner.py`
- `src/agents/claudecode/transcript.py`
