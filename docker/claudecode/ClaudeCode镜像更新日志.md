# Claude Code 镜像更新日志

本文记录 WildClawBench Claude Code Harness 的镜像版本、构建来源、运行方式和验证边界。正式构建映射维护在 `docker/claudecode/versions.json`。

## 当前正式镜像

| 记录日期 | 完整镜像 tag | Claude Code | Node.js | 构建来源 |
| --- | --- | --- | --- | --- |
| 2026-08-28 | `wildclawbench-claudecode-ubuntu:v0.3` | `2.1.250` | Node 24 | `docker/claudecode/v3/Dockerfile` |

### v0.3

- 改用官方全局包 `@anthropic-ai/claude-code@2.1.250`，命令为 `claude`。
- 从干净的 `wildclawbench-codex-ubuntu:v0.0` 评测底座重建，不继承旧 `v0.2-patched` 镜像层。
- 使用 `node:24-bookworm-slim` 提供 Node 24，满足 Claude Code 的 Node.js 版本要求。
- 保留底座中的 Google Chrome、Agent Browser、Playwright、Python、Git、jq 和文档处理工具。
- API key、base URL 和模型名只在任务容器启动时注入，镜像不包含运行时凭据或 `.env`。
- 无头执行使用 `--print --output-format stream-json`，原始 transcript 仍落在 `/claude_code/log/chat.json`，保持现有评分和产物收集路径兼容。
- Runner 会优先调用全局 `claude`，显式覆盖为历史镜像时仍可回退到 `/claude_code/start.sh`。

### 验证记录

- 镜像构建成功，镜像内 `claude --version` 为 `2.1.250`，Node.js 为 `v24.19.0`。
- 镜像内 Google Chrome `147.0.7727.101`、Agent Browser `0.26.0`、Python `3.11.15` 可用，且不存在 `/claude_code/.env` 和 `/root/.claude.json`。
- MaaS `xopglm52` 真实工具调用通过：Harness 正常退出，生成目标文件，转换轨迹包含一组配对的 `tool_use` / `tool_result`，usage 非零。
- `gpt-5.5` 真实调用到达 one-iflytek，但服务端连续返回 `503`，错误为当前分组无可用渠道；该结果不计为镜像或 runner 通过，也不归因于本次代码回归。
- ClaudeCode、transcript、镜像布局相关聚焦测试共 `52` 项通过。
- 完整单元测试执行 `620` 项，结果为 `54 failures + 1 error`；未修改主分支执行 `611` 项也为 `54 failures + 1 error`，逐项比较失败集合完全一致，因此只能说明本次升级没有新增单测失败，不能描述为全量测试通过。

构建命令：

```bash
bash docker/claudecode/build.sh --version v0.3 --skip-save
```

导出离线镜像时省略 `--skip-save`：

```bash
bash docker/claudecode/build.sh --version v0.3
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
export DOCKER_IMAGE_CLAUDECODE=wildclawbench-claudecode-ubuntu:v0.3
```

离线加载：

```bash
docker load -i Images/wildclawbench-claudecode-ubuntu_v0.3.tar.gz
```

## 相关实现

- `docker/claudecode/v3/Dockerfile`
- `docker/claudecode/versions.json`
- `docker/claudecode/build.sh`
- `src/agents/claudecode/runner.py`
- `src/agents/claudecode/transcript.py`
